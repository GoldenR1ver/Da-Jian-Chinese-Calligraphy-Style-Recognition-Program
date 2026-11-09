"""SQLite 字库：单字、变体、作者、风格、评分、单字图。"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterable, Optional

from .seed import AUTHORS, DIMENSIONS, SCRIPT_STYLES, VARIANTS

SCHEMA_VERSION = "1"

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dimensions (
    key TEXT PRIMARY KEY,
    name_zh TEXT NOT NULL,
    sort_order INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS script_styles (
    name TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS authors (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    era TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS author_aliases (
    alias TEXT PRIMARY KEY,
    author_id INTEGER NOT NULL REFERENCES authors(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS author_styles (
    id INTEGER PRIMARY KEY,
    author_id INTEGER NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
    style_name TEXT NOT NULL,
    UNIQUE (author_id, style_name)
);

CREATE TABLE IF NOT EXISTS style_scores (
    author_style_id INTEGER PRIMARY KEY REFERENCES author_styles(id) ON DELETE CASCADE,
    zhonghe REAL NOT NULL,
    duanzhuang REAL NOT NULL,
    dianya REAL NOT NULL,
    gupu REAL NOT NULL,
    gangjin REAL NOT NULL,
    xianjun REAL NOT NULL,
    satuo REAL NOT NULL,
    yanmei REAL NOT NULL,
    note TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY,
    canonical TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS character_variants (
    id INTEGER PRIMARY KEY,
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    form TEXT NOT NULL UNIQUE,
    variant_type TEXT NOT NULL CHECK (variant_type IN ('standard', 'traditional', 'simplified', 'variant'))
);

CREATE TABLE IF NOT EXISTS works (
    id INTEGER PRIMARY KEY,
    author_style_id INTEGER NOT NULL REFERENCES author_styles(id),
    title TEXT,
    source_path TEXT,
    layout TEXT NOT NULL,
    label_source TEXT NOT NULL,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS glyphs (
    id INTEGER PRIMARY KEY,
    work_id INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
    character_id INTEGER NOT NULL REFERENCES characters(id),
    variant_id INTEGER NOT NULL REFERENCES character_variants(id),
    author_style_id INTEGER NOT NULL REFERENCES author_styles(id),
    image BLOB NOT NULL,
    bbox_x INTEGER NOT NULL,
    bbox_y INTEGER NOT NULL,
    bbox_w INTEGER NOT NULL,
    bbox_h INTEGER NOT NULL,
    reading_order INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_glyphs_character ON glyphs(character_id);
CREATE INDEX IF NOT EXISTS idx_glyphs_style ON glyphs(author_style_id);
CREATE INDEX IF NOT EXISTS idx_variants_character ON character_variants(character_id);
"""


def default_db_path() -> Path:
    for key in ("CALLIGRAPHY_DB_PATH", "KOP_DATE_DB_PATH"):
        raw = os.environ.get(key)
        if raw and raw.strip():
            return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "data" / "calligraphy.db"


def connect(db_path: Optional[os.PathLike[str] | str] = None) -> sqlite3.Connection:
    path = Path(db_path).expanduser().resolve() if db_path else default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO meta(key, value) VALUES ('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (SCHEMA_VERSION,),
    )
    for order, (key, name) in enumerate(DIMENSIONS, start=1):
        conn.execute(
            "INSERT INTO dimensions(key, name_zh, sort_order) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET name_zh = excluded.name_zh, sort_order = excluded.sort_order",
            (key, name, order),
        )
    for name in SCRIPT_STYLES:
        conn.execute("INSERT OR IGNORE INTO script_styles(name) VALUES (?)", (name,))
    for canonical, era, aliases in AUTHORS:
        author_id = _ensure_author(conn, canonical, era)
        for alias in aliases:
            conn.execute(
                "INSERT INTO author_aliases(alias, author_id) VALUES (?, ?) "
                "ON CONFLICT(alias) DO UPDATE SET author_id = excluded.author_id",
                (alias, author_id),
            )
    for form, canonical, variant_type in VARIANTS:
        link_variant(conn, canonical, form, variant_type)
    conn.commit()


def _ensure_author(conn: sqlite3.Connection, name: str, era: Optional[str] = None) -> int:
    row = conn.execute("SELECT id, era FROM authors WHERE name = ?", (name,)).fetchone()
    if row:
        if era and not row["era"]:
            conn.execute("UPDATE authors SET era = ? WHERE id = ?", (era, row["id"]))
        return int(row["id"])
    cur = conn.execute("INSERT INTO authors(name, era) VALUES (?, ?)", (name, era))
    return int(cur.lastrowid)


def resolve_author_name(conn: sqlite3.Connection, name: str) -> str:
    cleaned = name.strip()
    row = conn.execute(
        """
        SELECT authors.name
        FROM author_aliases
        JOIN authors ON authors.id = author_aliases.author_id
        WHERE author_aliases.alias = ?
        """,
        (cleaned,),
    ).fetchone()
    if row:
        return str(row["name"])
    return cleaned


def ensure_author_style(conn: sqlite3.Connection, author_name: str, style_name: str, era: Optional[str] = None) -> int:
    canonical = resolve_author_name(conn, author_name)
    author_id = _ensure_author(conn, canonical, era)
    style = style_name.strip()
    if not canonical or not style:
        raise ValueError("作者和风格都不能为空")
    row = conn.execute(
        "SELECT id FROM author_styles WHERE author_id = ? AND style_name = ?",
        (author_id, style),
    ).fetchone()
    if row:
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO author_styles(author_id, style_name) VALUES (?, ?)",
        (author_id, style),
    )
    return int(cur.lastrowid)


def _ensure_character(conn: sqlite3.Connection, canonical: str) -> int:
    row = conn.execute("SELECT id FROM characters WHERE canonical = ?", (canonical,)).fetchone()
    if row:
        cid = int(row["id"])
    else:
        cur = conn.execute("INSERT INTO characters(canonical) VALUES (?)", (canonical,))
        cid = int(cur.lastrowid)
    conn.execute(
        "INSERT OR IGNORE INTO character_variants(character_id, form, variant_type) VALUES (?, ?, 'standard')",
        (cid, canonical),
    )
    return cid


def link_variant(conn: sqlite3.Connection, canonical: str, form: str, variant_type: str) -> tuple[int, int]:
    """把书写形归到规范字。返回 (character_id, variant_id)。"""
    canonical = canonical.strip()
    form = form.strip()
    if variant_type not in {"standard", "traditional", "simplified", "variant"}:
        raise ValueError(f"未知变体类型: {variant_type}")
    if not canonical or not form:
        raise ValueError("规范字和书写形都不能为空")
    if len(canonical) != 1 or len(form) != 1:
        raise ValueError("规范字和书写形都必须是单个汉字")
    if form == canonical:
        variant_type = "standard"

    character_id = _ensure_character(conn, canonical)
    existing = conn.execute(
        "SELECT id, character_id, variant_type FROM character_variants WHERE form = ?",
        (form,),
    ).fetchone()
    if existing and int(existing["character_id"]) != character_id:
        _rehome_form(conn, form, int(existing["character_id"]), character_id)
        existing = conn.execute(
            "SELECT id, character_id FROM character_variants WHERE form = ?",
            (form,),
        ).fetchone()
    if existing:
        conn.execute(
            "UPDATE character_variants SET variant_type = ?, character_id = ? WHERE id = ?",
            (variant_type, character_id, existing["id"]),
        )
        return character_id, int(existing["id"])
    cur = conn.execute(
        "INSERT INTO character_variants(character_id, form, variant_type) VALUES (?, ?, ?)",
        (character_id, form, variant_type),
    )
    return character_id, int(cur.lastrowid)


def _rehome_form(conn: sqlite3.Connection, form: str, old_character_id: int, new_character_id: int) -> None:
    """书写形原先被当成独立单字时，把样本改挂到新的规范字上。"""
    old = conn.execute("SELECT canonical FROM characters WHERE id = ?", (old_character_id,)).fetchone()
    if old and old["canonical"] != form:
        raise ValueError(f"「{form}」已经归到另一个规范字「{old['canonical']}」")
    variant = conn.execute(
        "SELECT id FROM character_variants WHERE form = ?",
        (form,),
    ).fetchone()
    if variant:
        conn.execute(
            "UPDATE glyphs SET character_id = ?, variant_id = ? WHERE variant_id = ?",
            (new_character_id, variant["id"], variant["id"]),
        )
        conn.execute(
            "UPDATE character_variants SET character_id = ? WHERE id = ?",
            (new_character_id, variant["id"]),
        )
    leftover = conn.execute(
        "SELECT COUNT(*) AS n FROM glyphs WHERE character_id = ?",
        (old_character_id,),
    ).fetchone()
    variants_left = conn.execute(
        "SELECT COUNT(*) AS n FROM character_variants WHERE character_id = ?",
        (old_character_id,),
    ).fetchone()
    if leftover and int(leftover["n"]) == 0 and variants_left and int(variants_left["n"]) == 0:
        conn.execute("DELETE FROM characters WHERE id = ?", (old_character_id,))


def lookup_form(conn: sqlite3.Connection, form: str) -> Optional[tuple[int, int, str]]:
    """只查询，不新建。比对用户作品时不能改动字库。"""
    row = conn.execute(
        """
        SELECT character_variants.id AS variant_id,
               characters.id AS character_id,
               characters.canonical AS canonical
        FROM character_variants
        JOIN characters ON characters.id = character_variants.character_id
        WHERE character_variants.form = ?
        """,
        (form.strip(),),
    ).fetchone()
    if not row:
        return None
    return int(row["character_id"]), int(row["variant_id"]), str(row["canonical"])


def resolve_form(conn: sqlite3.Connection, form: str) -> tuple[int, int, str]:
    """返回 (character_id, variant_id, canonical)。未见过的字按规范字新建。"""
    found = lookup_form(conn, form)
    if found:
        return found
    form = form.strip()
    character_id = _ensure_character(conn, form)
    variant = conn.execute(
        "SELECT id FROM character_variants WHERE form = ?",
        (form,),
    ).fetchone()
    return character_id, int(variant["id"]), form


def set_style_score(
    conn: sqlite3.Connection,
    author_name: str,
    style_name: str,
    scores: dict[str, float],
    note: Optional[str] = None,
) -> int:
    keys = [key for key, _ in DIMENSIONS]
    missing = [key for key in keys if key not in scores]
    if missing:
        raise ValueError("八维分数不完整")
    for key in keys:
        value = float(scores[key])
        if value < 0 or value > 100:
            raise ValueError(f"{key} 需要在 0 到 100 之间")
        scores[key] = value
    style_id = ensure_author_style(conn, author_name, style_name)
    conn.execute(
        f"""
        INSERT INTO style_scores(
            author_style_id, {", ".join(keys)}, note
        ) VALUES ({", ".join("?" for _ in range(len(keys) + 2))})
        ON CONFLICT(author_style_id) DO UPDATE SET
            {", ".join(f"{key}=excluded.{key}" for key in keys)},
            note=excluded.note,
            updated_at=CURRENT_TIMESTAMP
        """,
        (style_id, *[scores[key] for key in keys], note),
    )
    return style_id


def fetch_style_score(conn: sqlite3.Connection, author_style_id: int) -> Optional[dict]:
    row = conn.execute(
        f"""
        SELECT author_style_id, {", ".join(key for key, _ in DIMENSIONS)}, note
        FROM style_scores
        WHERE author_style_id = ?
        """,
        (author_style_id,),
    ).fetchone()
    return dict(row) if row else None


def iter_glyphs_for_canonical(conn: sqlite3.Connection, canonical: str) -> Iterable[sqlite3.Row]:
    return conn.execute(
        """
        SELECT glyphs.id AS glyph_id,
               glyphs.image AS image,
               authors.name AS author_name,
               author_styles.style_name AS style_name,
               author_styles.id AS author_style_id,
               characters.canonical AS canonical,
               character_variants.form AS form,
               character_variants.variant_type AS variant_type
        FROM glyphs
        JOIN characters ON characters.id = glyphs.character_id
        JOIN character_variants ON character_variants.id = glyphs.variant_id
        JOIN author_styles ON author_styles.id = glyphs.author_style_id
        JOIN authors ON authors.id = author_styles.author_id
        WHERE characters.canonical = ?
        ORDER BY glyphs.id
        """,
        (canonical,),
    )


def summary(conn: sqlite3.Connection) -> dict[str, int]:
    tables = {
        "authors": "SELECT COUNT(*) FROM authors",
        "author_styles": "SELECT COUNT(*) FROM author_styles",
        "scored_styles": "SELECT COUNT(*) FROM style_scores",
        "characters": "SELECT COUNT(*) FROM characters",
        "variants": "SELECT COUNT(*) FROM character_variants",
        "works": "SELECT COUNT(*) FROM works",
        "glyphs": "SELECT COUNT(*) FROM glyphs",
    }
    return {name: int(conn.execute(sql).fetchone()[0]) for name, sql in tables.items()}
