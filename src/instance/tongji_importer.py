from __future__ import annotations

import argparse
import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import cv2
import numpy as np

from . import get_kop_date_db_path


DEFAULT_DATASET_ROOT = (
    Path(__file__).resolve().parents[2]
    / "res"
    / "chinese-calligraphy-dataset"
    / "chinese-calligraphy-dataset-with-calligrapher"
)


def _is_cjk_char(ch: str) -> bool:
    if len(ch) != 1:
        return False
    cp = ord(ch)
    return (
        0x4E00 <= cp <= 0x9FFF
        or 0x3400 <= cp <= 0x4DBF
        or 0x20000 <= cp <= 0x2A6DF
        or 0x2A700 <= cp <= 0x2B73F
        or 0x2B740 <= cp <= 0x2B81F
        or 0x2B820 <= cp <= 0x2CEAF
        or 0xF900 <= cp <= 0xFAFF
    )


def _norm_rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _style_author_from_dir(name: str) -> tuple[Optional[str], Optional[str]]:
    # Expected format in Tongji set: "隶-金农", "行-米芾", ...
    if "-" not in name:
        return None, name or None
    style_prefix, author = name.split("-", 1)
    style_prefix = style_prefix.strip()
    author = author.strip()
    style_map = {
        "楷": "楷书",
        "行": "行书",
        "隶": "隶书",
        "草": "草书",
        "篆": "篆书",
    }
    style = style_map.get(style_prefix, style_prefix or None)
    return style, author or None


def _guess_mime(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext == ".gif":
        return "image/gif"
    if ext == ".png":
        return "image/png"
    return "application/octet-stream"


def _iter_image_files(root: Path, exts: set[str]) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            yield p


@dataclass
class ImportStats:
    scanned_files: int = 0
    inserted_rows: int = 0
    skipped_non_cjk_dir: int = 0
    skipped_bad_layout: int = 0
    skipped_invalid_image: int = 0
    skipped_already_imported: int = 0


def _ensure_registry_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS import_registry_tongji (
            source_rel_path TEXT PRIMARY KEY,
            sha256 TEXT NOT NULL,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_import_registry_tongji_sha256
        ON import_registry_tongji(sha256)
        """
    )
    conn.commit()


def import_tongji_dataset(
    dataset_root: Path,
    db_path: Optional[str] = None,
    *,
    commit_every: int = 500,
    limit: Optional[int] = None,
) -> ImportStats:
    stats = ImportStats()
    root = dataset_root.resolve()
    if not root.exists():
        raise FileNotFoundError(f"Dataset root not found: {root}")

    target_db = Path(db_path).expanduser().resolve() if db_path else get_kop_date_db_path()
    with sqlite3.connect(str(target_db)) as conn:
        _ensure_registry_table(conn)
        existing = {
            r[0]
            for r in conn.execute("SELECT source_rel_path FROM import_registry_tongji").fetchall()
        }
        inserted_since_commit = 0

        for image_path in _iter_image_files(root, exts={".gif", ".jpg", ".jpeg", ".png"}):
            stats.scanned_files += 1
            if limit is not None and stats.scanned_files > int(limit):
                break

            rel = _norm_rel(image_path, root)
            if rel in existing:
                stats.skipped_already_imported += 1
                continue

            # Expected path: <style-author>/<char>/<file>
            parts = image_path.resolve().relative_to(root).parts
            if len(parts) < 3:
                stats.skipped_bad_layout += 1
                continue
            style_author_dir = parts[-3]
            char_dir = parts[-2].strip()
            if not _is_cjk_char(char_dir):
                stats.skipped_non_cjk_dir += 1
                continue

            style, author = _style_author_from_dir(style_author_dir)
            blob = image_path.read_bytes()
            if not blob:
                stats.skipped_invalid_image += 1
                continue

            # Quick validity check: image bytes should be decodable by OpenCV path later.
            arr = np.frombuffer(blob, dtype=np.uint8)
            decoded = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
            if decoded is None:
                stats.skipped_invalid_image += 1
                continue

            registry_cur = conn.execute(
                """
                INSERT OR IGNORE INTO import_registry_tongji (source_rel_path, sha256)
                VALUES (?, ?)
                """,
                (rel, hashlib.sha256(blob).hexdigest()),
            )
            if registry_cur.rowcount == 0:
                stats.skipped_already_imported += 1
                continue

            conn.execute(
                """
                INSERT INTO characters (
                    character, author_name, style, svg, image_data, image_type, is_svg
                )
                VALUES (?, ?, ?, NULL, ?, ?, 0)
                """,
                (char_dir, author, style, blob, _guess_mime(image_path)),
            )
            existing.add(rel)
            stats.inserted_rows += 1
            inserted_since_commit += 1

            if inserted_since_commit >= commit_every:
                conn.commit()
                inserted_since_commit = 0

        conn.commit()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Tongji Chinese calligraphy dataset into characters table.")
    parser.add_argument(
        "--dataset-root",
        default=str(DEFAULT_DATASET_ROOT),
        help="Root directory of Tongji dataset (style-author/char/*.gif)",
    )
    parser.add_argument("--db-path", default=None, help="Optional custom db path")
    parser.add_argument("--commit-every", type=int, default=500, help="Commit every N inserted rows")
    parser.add_argument("--limit", type=int, default=None, help="Optional max scanned files (debug)")
    args = parser.parse_args()

    stats = import_tongji_dataset(
        Path(args.dataset_root),
        db_path=args.db_path,
        commit_every=max(1, int(args.commit_every)),
        limit=args.limit,
    )
    print(
        "Imported Tongji dataset: "
        f"scanned={stats.scanned_files}, inserted={stats.inserted_rows}, "
        f"skip_non_cjk={stats.skipped_non_cjk_dir}, "
        f"skip_layout={stats.skipped_bad_layout}, "
        f"skip_invalid={stats.skipped_invalid_image}, "
        f"skip_already_imported={stats.skipped_already_imported}"
    )


if __name__ == "__main__":
    main()

