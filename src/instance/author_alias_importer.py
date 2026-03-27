from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Optional

from ..character_matcher.repository import db_connection, ensure_style_tables
from .author_alias_rules import load_alias_rules_file


PREFIX_RE = re.compile(r"^(楷书|行书|隶书|草书|篆书|钢楷|标楷体)\s*[-－]\s*(.+)$")


def _canonical_name(author_name: str) -> str:
    name = author_name.strip()
    m = PREFIX_RE.match(name)
    if m:
        return m.group(2).strip()
    return name


def import_manual_rules(conn, rules_path: Path) -> int:
    pairs = load_alias_rules_file(rules_path)
    count = 0
    for alias, canonical in pairs:
        conn.execute(
            """
            INSERT INTO author_alias(alias_name, canonical_name)
            VALUES (?, ?)
            ON CONFLICT(alias_name) DO UPDATE SET canonical_name=excluded.canonical_name
            """,
            (alias, canonical),
        )
        count += 1
    return count


def import_prefix_rules_from_characters(conn) -> int:
    rows = conn.execute(
        "SELECT DISTINCT author_name FROM characters WHERE author_name IS NOT NULL AND trim(author_name) != ''"
    ).fetchall()
    count = 0
    for row in rows:
        alias = row["author_name"].strip()
        canonical = _canonical_name(alias)
        if alias == canonical:
            continue
        conn.execute(
            """
            INSERT INTO author_alias(alias_name, canonical_name)
            VALUES (?, ?)
            ON CONFLICT(alias_name) DO UPDATE SET canonical_name=excluded.canonical_name
            """,
            (alias, canonical),
        )
        count += 1
    return count


def import_author_aliases(
    db_path: Optional[str] = None,
    *,
    rules_file: Optional[Path] = None,
    skip_prefix_heuristic: bool = False,
) -> tuple[int, int]:
    """Return (manual_rule_count, prefix_heuristic_count)."""
    default_rules = Path(__file__).resolve().parent / "author_alias_rules.txt"
    path = rules_file if rules_file is not None else default_rules
    manual = 0
    prefix = 0
    with db_connection(db_path) as conn:
        ensure_style_tables(conn)
        manual = import_manual_rules(conn, path)
        if not skip_prefix_heuristic:
            prefix = import_prefix_rules_from_characters(conn)
        conn.commit()
    return manual, prefix


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import author alias rules: optional author_alias_rules.txt then DB prefix heuristics."
    )
    parser.add_argument("--db-path", default=None, help="Optional custom db path")
    parser.add_argument(
        "--rules-file",
        default=None,
        help="Path to alias|canonical rules file (default: src/instance/author_alias_rules.txt)",
    )
    parser.add_argument(
        "--skip-prefix-heuristic",
        action="store_true",
        help="Only apply manual rules file, do not infer 行书-xxx -> xxx from characters",
    )
    args = parser.parse_args()
    rules: Optional[Path] = None
    if args.rules_file:
        p = Path(args.rules_file).expanduser().resolve()
        if not p.is_file():
            raise SystemExit(f"Rules file not found: {p}")
        rules = p
    manual, prefix = import_author_aliases(
        db_path=args.db_path,
        rules_file=rules,
        skip_prefix_heuristic=args.skip_prefix_heuristic,
    )
    print(f"Manual rules applied: {manual}, prefix-heuristic rows: {prefix}")


if __name__ == "__main__":
    main()
