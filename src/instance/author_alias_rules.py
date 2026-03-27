"""Parse optional author_alias_rules.txt (alias|canonical)."""

from __future__ import annotations

from pathlib import Path


def load_alias_rules_file(path: Path) -> list[tuple[str, str]]:
    if not path.is_file():
        return []
    pairs: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            continue
        left, right = line.split("|", 1)
        alias = left.strip()
        canonical = right.strip()
        if alias and canonical:
            pairs.append((alias, canonical))
    return pairs
