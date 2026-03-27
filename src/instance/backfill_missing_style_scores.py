from __future__ import annotations

import argparse
from collections import Counter
from typing import Optional

from ..character_matcher.repository import STYLE_DIMENSIONS, db_connection, ensure_style_tables


# 作品名/异名 -> 已有评分条目
EXPLICIT_DONOR_MAP: dict[str, str] = {
    "张猛龙碑": "《张猛龙碑》",
    "会稽刻石": "《会稽刻石》",
    "月仪帖": "《月仪帖》",
    "北海王造像": "《龙门造像》（北海王等）",
    "高贞碑": "《高贞碑》《李璧碑》",
    "李璧碑": "《高贞碑》《李璧碑》",
    "石婉墓志": "《石婉墓志》",
    "马王堆帛书": "《马王堆帛书》",
    "虢季子白盘": "《虢季子白盘》",
    "曹全碑": "《曹全碑》",
    "衡方碑": "《衡方碑》",
    "多宝塔": "《多宝塔碑》",
    "颜家庙碑": "颜真卿《颜家庙碑》",
    "集字圣教序": "王羲之《集字圣教序》",
    "行书-集字圣教序": "王羲之《集字圣教序》",
    "赵孟俯三门记": "赵孟頫《三门记》",
    "赵孟頫三门记体": "赵孟頫《三门记》",
    "颜真卿多宝塔体": "《多宝塔碑》",
    "唐玄宗": "李隆基（唐玄宗）",
    "李隆基": "李隆基（唐玄宗）",
    "冯承素": "王羲之《兰亭序》（冯承素摹本）",
    "魏碑": "魏碑（泛称）",
    "颜真卿": "颜真卿（整体）",
    "赵孟頫": "赵孟頫（整体）",
    "文征明": "文徵明",
    "祝枝山": "祝允明",
    "陈淳": "陈淳（陈道复）",
    "陈道复": "陈淳（陈道复）",
    "朱耷": "朱耷（八大山人）",
    "行书-米芾": "米芾（行书）",
    "隶书-邓石如": "邓石如",
    "隶书-伊秉绶": "伊秉绶",
    "隶书-何绍基": "何绍基",
}

# 一些仅在数据集中出现的风格标签，映射到稳定原型
STYLE_DONOR_MAP: dict[str, str] = {
    "楷书": "颜真卿（整体）",
    "行书": "王羲之",
    "草书": "怀素",
    "隶书": "《曹全碑》",
    "篆书": "《会稽刻石》",
    "魏碑": "魏碑（泛称）",
}

# 个别作者显式指定“近似风格原型”
AUTHOR_FALLBACK_MAP: dict[str, str] = {
    "金农": "郑板桥",
    "隶书-金农": "郑板桥",
    "吴大澂": "吴大澂/吴大澄",
    "吴大澄": "吴大澂/吴大澄",
    "祝枝山": "祝允明",
    "沈尹默": "王羲之",
    "王慈": "王坦之、王慈等王氏子弟",
    "王坦之": "王坦之、王慈等王氏子弟",
    "王升": "王坦之、王慈等王氏子弟",
    "王壮为": "王羲之",
    "陈献章": "倪元璐",
    "包世臣": "康有为",
    "方去疾": "吴昌硕",
    "现代方去疾": "吴昌硕",
    "现代林时九": "《标准草书》",
    "不详": "王羲之",
    "古人": "王羲之",
    "近人": "《标准草书》",
    "明人": "文徵明",
    "清人": "邓石如",
}


def _load_existing_scores(conn) -> dict[str, dict]:
    rows = conn.execute(
        f"SELECT author_name, era, {', '.join(STYLE_DIMENSIONS)}, note FROM author_style_scores"
    ).fetchall()
    return {row["author_name"]: dict(row) for row in rows}


def _dominant_style(conn, author_name: str) -> Optional[str]:
    rows = conn.execute(
        """
        SELECT style, COUNT(*) AS c
        FROM characters
        WHERE author_name = ?
          AND style IS NOT NULL
          AND TRIM(style) != ''
        GROUP BY style
        ORDER BY c DESC
        """,
        (author_name,),
    ).fetchall()
    if not rows:
        return None
    return rows[0]["style"]


def _donor_from_name(author_name: str, existing: dict[str, dict]) -> Optional[str]:
    if author_name in EXPLICIT_DONOR_MAP:
        return EXPLICIT_DONOR_MAP[author_name]
    if author_name in AUTHOR_FALLBACK_MAP:
        return AUTHOR_FALLBACK_MAP[author_name]
    if author_name.startswith("行书-"):
        return "王羲之"
    if author_name.startswith("楷书-"):
        return "颜真卿（整体）"
    if author_name.startswith("草书-"):
        return "怀素"
    if author_name.startswith("隶书-"):
        return "《曹全碑》"
    if author_name.startswith("篆书-"):
        return "《会稽刻石》"
    wrapped = f"《{author_name}》"
    if wrapped in existing:
        return wrapped
    return None


def backfill_missing_scores(db_path: Optional[str] = None, *, dry_run: bool = False) -> tuple[int, int]:
    with db_connection(db_path) as conn:
        ensure_style_tables(conn)
        existing = _load_existing_scores(conn)
        missing = [
            row["author_name"]
            for row in conn.execute(
                """
                SELECT DISTINCT author_name
                FROM characters
                WHERE author_name IS NOT NULL
                  AND TRIM(author_name) != ''
                  AND author_name NOT IN (SELECT author_name FROM author_style_scores)
                ORDER BY author_name
                """
            ).fetchall()
        ]

        inserted = 0
        unresolved = 0
        donor_counter: Counter[str] = Counter()
        for author in missing:
            donor = _donor_from_name(author, existing)
            if donor is None:
                dom_style = _dominant_style(conn, author)
                if dom_style:
                    donor = STYLE_DONOR_MAP.get(dom_style)
            if donor is None:
                donor = "王羲之"
            if donor not in existing:
                unresolved += 1
                continue
            row = existing[donor]
            donor_counter[donor] += 1
            if dry_run:
                continue
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
                    author,
                    row["era"],
                    row["zhonghe"],
                    row["duanzhuang"],
                    row["dianya"],
                    row["gupu"],
                    row["gangjin"],
                    row["xianjun"],
                    row["satuo"],
                    row["yanmei"],
                    f"Auto-backfilled from donor: {donor}",
                    "auto_backfill_20260327",
                ),
            )
            inserted += 1

        if not dry_run:
            conn.commit()

    return inserted, unresolved


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill missing author_style_scores from known prototypes.")
    parser.add_argument("--db-path", default=None, help="Optional custom db path")
    parser.add_argument("--dry-run", action="store_true", help="Do not write DB, only count resolvable items")
    args = parser.parse_args()

    inserted, unresolved = backfill_missing_scores(db_path=args.db_path, dry_run=args.dry_run)
    mode = "DRY-RUN" if args.dry_run else "WRITE"
    print(f"[{mode}] inserted={inserted}, unresolved={unresolved}")


if __name__ == "__main__":
    main()
