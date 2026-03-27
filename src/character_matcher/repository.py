from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from ..instance import get_kop_date_db_path


@dataclass
class GlyphSample:
    sample_id: int
    char: str
    author_name: Optional[str]
    style: Optional[str]
    svg: Optional[str]
    image_data: Optional[bytes]
    image_type: Optional[str]
    is_svg: bool


STYLE_DIMENSIONS = (
    "zhonghe",
    "duanzhuang",
    "dianya",
    "gupu",
    "gangjin",
    "xianjun",
    "satuo",
    "yanmei",
)

# 报告雷达图与「书法八维」评语使用的八个维度（与 STYLE_DIMENSIONS 一致）
EIGHT_DIMENSION_KEYS = STYLE_DIMENSIONS


@contextmanager
def db_connection(db_path: Optional[str] = None) -> Iterator[sqlite3.Connection]:
    path = Path(db_path).expanduser().resolve() if db_path else get_kop_date_db_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def ensure_style_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS author_style_scores (
            author_name TEXT PRIMARY KEY,
            era TEXT,
            zhonghe REAL,
            duanzhuang REAL,
            dianya REAL,
            gupu REAL,
            gangjin REAL,
            xianjun REAL,
            satuo REAL,
            yanmei REAL,
            note TEXT,
            source TEXT DEFAULT 'manual_v1',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS author_alias (
            alias_name TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL
        )
        """
    )
    conn.commit()


def normalize_author_name(conn: sqlite3.Connection, author_name: Optional[str]) -> Optional[str]:
    if not author_name:
        return author_name
    row = conn.execute(
        "SELECT canonical_name FROM author_alias WHERE alias_name = ?",
        (author_name,),
    ).fetchone()
    return row["canonical_name"] if row else author_name


def fetch_glyph_samples_by_char(
    conn: sqlite3.Connection, char: str, limit: int = 120
) -> list[GlyphSample]:
    rows = conn.execute(
        """
        SELECT
            character_id,
            character,
            author_name,
            style,
            svg,
            image_data,
            image_type,
            is_svg
        FROM characters
        WHERE character = ?
        LIMIT ?
        """,
        (char, int(limit)),
    ).fetchall()
    samples: list[GlyphSample] = []
    for row in rows:
        samples.append(
            GlyphSample(
                sample_id=int(row["character_id"]),
                char=str(row["character"]),
                author_name=row["author_name"],
                style=row["style"],
                svg=row["svg"],
                image_data=row["image_data"],
                image_type=row["image_type"],
                is_svg=bool(row["is_svg"]),
            )
        )
    return samples


def fetch_glyph_sample_by_id(conn: sqlite3.Connection, sample_id: int) -> Optional[GlyphSample]:
    row = conn.execute(
        """
        SELECT
            character_id,
            character,
            author_name,
            style,
            svg,
            image_data,
            image_type,
            is_svg
        FROM characters
        WHERE character_id = ?
        """,
        (sample_id,),
    ).fetchone()
    if not row:
        return None
    return GlyphSample(
        sample_id=int(row["character_id"]),
        char=str(row["character"]),
        author_name=row["author_name"],
        style=row["style"],
        svg=row["svg"],
        image_data=row["image_data"],
        image_type=row["image_type"],
        is_svg=bool(row["is_svg"]),
    )


def fetch_author_style_scores(conn: sqlite3.Connection, author_name: str) -> Optional[dict]:
    canonical_name = normalize_author_name(conn, author_name)
    try:
        row = conn.execute(
            """
            SELECT author_name, era, zhonghe, duanzhuang, dianya, gupu, gangjin, xianjun, satuo, yanmei, note, source
            FROM author_style_scores
            WHERE author_name = ?
            """,
            (canonical_name,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    return dict(row) if row else None
