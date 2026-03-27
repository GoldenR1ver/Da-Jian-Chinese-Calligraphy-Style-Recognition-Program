from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional

from ..character_matcher.repository import STYLE_DIMENSIONS, db_connection, ensure_style_tables


def _cleanup_cell(text: str) -> str:
    s = text.strip()
    s = s.replace("**", "").replace("`", "")
    return s


def _to_float(token: str) -> Optional[float]:
    raw = _cleanup_cell(token)
    if not raw:
        return None
    if "-" in raw:
        left = raw.split("-", 1)[0].strip()
        raw = left
    if not re.match(r"^\d+(\.\d+)?$", raw):
        return None
    return float(raw)


def parse_style_markdown(markdown_path: Path) -> list[dict]:
    lines = markdown_path.read_text(encoding="utf-8").splitlines()
    rows: list[dict] = []
    for line in lines:
        if not line.strip().startswith("|"):
            continue
        if "---" in line:
            continue
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) < 11:
            continue
        author = _cleanup_cell(parts[0])
        if author in ("书法家/作品", ""):
            continue
        era = _cleanup_cell(parts[1]) or None
        numbers = [_to_float(x) for x in parts[2:10]]
        if any(v is None for v in numbers):
            continue
        rows.append(
            {
                "author_name": author,
                "era": era,
                "zhonghe": numbers[0],
                "duanzhuang": numbers[1],
                "dianya": numbers[2],
                "gupu": numbers[3],
                "gangjin": numbers[4],
                "xianjun": numbers[5],
                "satuo": numbers[6],
                "yanmei": numbers[7],
                "note": _cleanup_cell(parts[10]) if len(parts) > 10 else None,
                "source": "书法作品打分.md",
            }
        )
    return rows


def import_style_scores(markdown_path: Path, db_path: Optional[str] = None) -> int:
    rows = parse_style_markdown(markdown_path)
    if not rows:
        return 0
    with db_connection(db_path) as conn:
        ensure_style_tables(conn)
        for row in rows:
            conn.execute(
                f"""
                INSERT INTO author_style_scores (
                    author_name, era, {", ".join(STYLE_DIMENSIONS)}, note, source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(author_name) DO UPDATE SET
                    era=excluded.era,
                    zhonghe=excluded.zhonghe,
                    duanzhuang=excluded.duanzhuang,
                    dianya=excluded.dianya,
                    gupu=excluded.gupu,
                    gangjin=excluded.gangjin,
                    xianjun=excluded.xianjun,
                    satuo=excluded.satuo,
                    yanmei=excluded.yanmei,
                    note=excluded.note,
                    source=excluded.source,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    row["author_name"],
                    row["era"],
                    row["zhonghe"],
                    row["duanzhuang"],
                    row["dianya"],
                    row["gupu"],
                    row["gangjin"],
                    row["xianjun"],
                    row["satuo"],
                    row["yanmei"],
                    row["note"],
                    row["source"],
                ),
            )
        conn.commit()
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import style score markdown into SQLite table.")
    parser.add_argument(
        "--markdown",
        default=str(Path(__file__).resolve().parent / "书法作品打分.md"),
        help="Path to markdown table file",
    )
    parser.add_argument("--db-path", default=None, help="Optional custom db path")
    args = parser.parse_args()
    n = import_style_scores(Path(args.markdown), db_path=args.db_path)
    print(f"Imported {n} style-score rows.")


if __name__ == "__main__":
    main()
