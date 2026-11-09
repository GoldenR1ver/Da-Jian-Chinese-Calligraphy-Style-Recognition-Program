"""命令行入口。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import analyze, db, ingest
from .seed import DIMENSIONS, SCRIPT_STYLES


def _open(path: str | None):
    conn = db.connect(path)
    db.initialize(conn)
    return conn


def _print_status(conn, path: Path) -> None:
    counts = db.summary(conn)
    print(f"数据库: {path}")
    print(
        f"作者 {counts['authors']}  风格 {counts['author_styles']}  "
        f"已评分 {counts['scored_styles']}  单字 {counts['characters']}  "
        f"变体 {counts['variants']}  作品 {counts['works']}  单字样本 {counts['glyphs']}"
    )
    styles = conn.execute("SELECT name FROM script_styles ORDER BY name").fetchall()
    print("常见书体: " + "、".join(row["name"] for row in styles))


def _parse_scores(raw: str) -> dict[str, float]:
    parts = [item.strip() for item in raw.replace("，", ",").split(",") if item.strip()]
    keys = [key for key, _ in DIMENSIONS]
    if len(parts) != len(keys):
        names = "、".join(name for _, name in DIMENSIONS)
        raise ValueError(f"--scores 需要 {len(keys)} 个分数，顺序是 {names}")
    return {key: float(value) for key, value in zip(keys, parts)}


def _cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.db).expanduser().resolve() if args.db else db.default_db_path()
    conn = _open(str(path))
    try:
        _print_status(conn, path)
    finally:
        conn.close()
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    path = Path(args.db).expanduser().resolve() if args.db else db.default_db_path()
    if not path.exists():
        print(f"还没有数据库。先运行: python -m calligraphy_style init", file=sys.stderr)
        return 1
    conn = _open(str(path))
    try:
        _print_status(conn, path)
        rows = conn.execute(
            """
            SELECT authors.name AS author, author_styles.style_name AS style,
                   COUNT(glyphs.id) AS glyphs,
                   CASE WHEN style_scores.author_style_id IS NULL THEN 0 ELSE 1 END AS scored
            FROM author_styles
            JOIN authors ON authors.id = author_styles.author_id
            LEFT JOIN glyphs ON glyphs.author_style_id = author_styles.id
            LEFT JOIN style_scores ON style_scores.author_style_id = author_styles.id
            GROUP BY author_styles.id
            ORDER BY authors.name, author_styles.style_name
            """
        ).fetchall()
        if rows:
            print("作者风格:")
            for row in rows:
                mark = "已评分" if row["scored"] else "未评分"
                print(f"  {row['author']} / {row['style']}  样本 {row['glyphs']}  {mark}")
    finally:
        conn.close()
    return 0


def _cmd_import(args: argparse.Namespace) -> int:
    conn = _open(args.db)
    try:
        result = ingest.import_work(
            conn,
            Path(args.image),
            args.author,
            args.style,
            title=args.title,
            text=args.text,
            use_baidu=args.ocr == "baidu",
            layout=args.layout,
            api_key=args.baidu_api_key,
            secret_key=args.baidu_secret_key,
            debug_dir=Path(args.debug_dir) if args.debug_dir else None,
        )
    finally:
        conn.close()
    forms = "".join(item.form for item in result.glyphs)
    canonical = "".join(item.canonical for item in result.glyphs)
    print(f"作品 #{result.work_id}  {result.author} / {result.style}")
    print(f"标签来源: {result.label_source}  字数: {len(result.glyphs)}")
    print(f"书写: {forms}")
    if canonical != forms:
        print(f"规范: {canonical}")
    return 0


def _cmd_variant(args: argparse.Namespace) -> int:
    conn = _open(args.db)
    try:
        if args.variant_cmd == "add":
            db.link_variant(conn, args.canonical, args.form, args.type)
            conn.commit()
            print(f"已登记 {args.form} → {args.canonical} ({args.type})")
            return 0
        if args.variant_cmd == "import":
            count = 0
            for line in Path(args.file).read_text(encoding="utf-8").splitlines():
                raw = line.strip()
                if not raw or raw.startswith("#"):
                    continue
                parts = [item.strip() for item in raw.replace("，", ",").replace("\t", ",").split(",")]
                if parts[0] in {"规范字", "canonical"}:
                    continue
                if len(parts) != 3:
                    raise ValueError(f"无法解析变体行: {line}")
                canonical, form, variant_type = parts
                db.link_variant(conn, canonical, form, variant_type)
                count += 1
            conn.commit()
            print(f"导入变体 {count} 条")
            return 0
    finally:
        conn.close()
    return 2


def _cmd_score(args: argparse.Namespace) -> int:
    conn = _open(args.db)
    try:
        scores = _parse_scores(args.scores)
        db.set_style_score(conn, args.author, args.style, scores, note=args.note)
        conn.commit()
        author = db.resolve_author_name(conn, args.author)
        print(f"已写入 {author} / {args.style.strip()} 的八维评分")
    finally:
        conn.close()
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    conn = _open(args.db)
    try:
        report = analyze.analyze_image(
            conn,
            Path(args.image),
            text=args.text,
            use_baidu=args.ocr == "baidu",
            layout=args.layout,
        )
    finally:
        conn.close()
    print(report["summary"])
    if report["authors"]:
        print("接近的作者风格:")
        for item in report["authors"]:
            chars = "".join(item["chars"])
            print(f"  {item['author']} / {item['style']}  分数 {item['score']}  票数 {item['votes']}  字 {chars}")
    else:
        print("没有超过阈值的书家。")
    if report["eight_dimensions"]:
        text = "  ".join(f"{name} {value}" for name, value in report["eight_dimensions"].items())
        print("八维: " + text)
    for glyph in report["glyphs"]:
        if not glyph["candidates"]:
            print(f"  {glyph['form']}（{glyph['canonical']}）  字库无样本")
            continue
        best = glyph["candidates"][0]
        print(f"  {glyph['form']}（{glyph['canonical']}）  {best['author']} / {best['style']}  {best['score']}")
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"报告: {args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="calligraphy_style",
        description="书法字库与风格比对。先 init，再 import 作品，然后 analyze。",
    )
    parser.add_argument("--db", default=None, help="数据库路径，默认 data/calligraphy.db")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="创建或补齐默认数据库").set_defaults(func=_cmd_init)
    sub.add_parser("status", help="查看字库规模").set_defaults(func=_cmd_status)

    import_cmd = sub.add_parser("import", help="导入一幅书法作品：切字、清洗、入库")
    import_cmd.add_argument("--image", required=True)
    import_cmd.add_argument("--author", required=True)
    import_cmd.add_argument("--style", required=True, help=f"例如 {'、'.join(SCRIPT_STYLES)}，也可以自定名称")
    import_cmd.add_argument("--title", default=None)
    import_cmd.add_argument("--text", default=None, help="按阅读顺序写的释文，标点会忽略")
    import_cmd.add_argument("--ocr", choices=["baidu"], default=None)
    import_cmd.add_argument("--layout", choices=["horizontal", "vertical"], default="horizontal")
    import_cmd.add_argument("--debug-dir", default=None, help="把切出的单字图写到这个目录")
    import_cmd.add_argument("--baidu-api-key", default=None)
    import_cmd.add_argument("--baidu-secret-key", default=None)
    import_cmd.set_defaults(func=_cmd_import)

    variant = sub.add_parser("variant", help="登记繁体或异体")
    variant_sub = variant.add_subparsers(dest="variant_cmd", required=True)
    add = variant_sub.add_parser("add")
    add.add_argument("--canonical", required=True)
    add.add_argument("--form", required=True)
    add.add_argument("--type", required=True, choices=["traditional", "simplified", "variant", "standard"])
    add.set_defaults(func=_cmd_variant)
    bulk = variant_sub.add_parser("import")
    bulk.add_argument("--file", required=True, help="CSV/TSV：规范字,书写形,类型")
    bulk.set_defaults(func=_cmd_variant)

    score = sub.add_parser("score", help="写入某个作者风格的八维分数")
    score.add_argument("--author", required=True)
    score.add_argument("--style", required=True)
    score.add_argument("--scores", required=True, help="八个 0–100 的数，逗号分隔，顺序见 README")
    score.add_argument("--note", default=None)
    score.set_defaults(func=_cmd_score)

    analyze_cmd = sub.add_parser("analyze", help="比对一张新作品")
    analyze_cmd.add_argument("--image", required=True)
    analyze_cmd.add_argument("--text", default=None)
    analyze_cmd.add_argument("--ocr", choices=["baidu"], default=None)
    analyze_cmd.add_argument("--layout", choices=["horizontal", "vertical"], default="horizontal")
    analyze_cmd.add_argument("--out", default=None, help="把 JSON 报告写到这个路径")
    analyze_cmd.set_defaults(func=_cmd_analyze)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
