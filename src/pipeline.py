from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from .character_matcher.matcher import MatcherConfig, enrich_bundle_with_db_matches
from .character_matcher.schema import BoundingBox, MatchBundle, SingleCharMatch
from .instance.style_score_importer import import_style_scores
from .ocr_recognizer import ocr_recognize, parse_ocr_result
from .report_generator import generate_complete_style_report, render_style_report_html


def _resolve_ocr_provider_default() -> str:
    """Resolve OCR provider default from env, fallback to baidu."""
    provider = (
        os.getenv("CALLIGRAPHY_OCR_PROVIDER")
        or os.getenv("OCR_PROVIDER")
        or "baidu"
    ).strip().lower()
    if provider not in {"local_hwdb", "baidu"}:
        return "baidu"
    return provider


def ocr_to_match_bundle(
    image_path: str,
    *,
    ocr_provider: str = "baidu",
    baidu_api_key: Optional[str] = None,
    baidu_secret_key: Optional[str] = None,
    local_model_name: str = "ResNet",
    local_model_path: Optional[str] = None,
    local_char_dict_path: Optional[str] = None,
    local_use_cuda: bool = False,
    with_db_match: bool = True,
    sample_limit_per_char: int = 120,
    feature_prefilter_limit: int = 40,
    top_k_per_char: int = 5,
    top_n_authors: int = 5,
    min_score_to_vote: float = 45.0,
    db_path: Optional[str] = None,
) -> MatchBundle:
    if ocr_provider == "local_hwdb":
        from .ocr_recognizer.local_hwdb import LocalHwdbConfig, LocalHwdbOcrEngine

        engine = LocalHwdbOcrEngine(
            LocalHwdbConfig(
                model_name=local_model_name,
                model_path=local_model_path,
                char_dict_path=local_char_dict_path,
                use_cuda=local_use_cuda,
            )
        )
        raw = engine.recognize(image_path)
    elif ocr_provider == "baidu":
        baidu_api_key = baidu_api_key or os.getenv("BAIDU_OCR_API_KEY")
        baidu_secret_key = baidu_secret_key or os.getenv("BAIDU_OCR_SECRET_KEY")
        if not baidu_api_key or not baidu_secret_key:
            raise ValueError(
                "baidu provider requires baidu_api_key and baidu_secret_key "
                "(or env BAIDU_OCR_API_KEY / BAIDU_OCR_SECRET_KEY)"
            )
        raw = ocr_recognize(image_path, baidu_api_key, baidu_secret_key)
    else:
        raise ValueError(f"Unsupported ocr_provider: {ocr_provider}")

    parsed = parse_ocr_result(raw)

    bundle = MatchBundle(
        version="0.1.0",
        image_path=image_path,
        ocr_engine=str(raw.get("ocr_engine", ocr_provider)),
    )

    for line in parsed:
        for ch in line.get("chars", []):
            loc = ch.get("location")
            bbox: Optional[BoundingBox] = None
            if isinstance(loc, dict):
                bbox = BoundingBox(
                    left=int(loc.get("left", 0)),
                    top=int(loc.get("top", 0)),
                    width=int(loc.get("width", 0)),
                    height=int(loc.get("height", 0)),
                )
            bundle.chars.append(
                SingleCharMatch(
                    char=ch.get("char", "")[:1],
                    location=bbox,
                    candidates=[],
                )
            )

    if with_db_match:
        bundle = enrich_bundle_with_db_matches(
            bundle,
            MatcherConfig(
                sample_limit_per_char=sample_limit_per_char,
                feature_prefilter_limit=feature_prefilter_limit,
                top_k_per_char=top_k_per_char,
                top_n_authors=top_n_authors,
                min_score_to_vote=min_score_to_vote,
                db_path=db_path,
            ),
        )

    return bundle


def _model_to_dict(model_obj: object) -> dict:
    if hasattr(model_obj, "model_dump"):
        return model_obj.model_dump()  # pydantic v2
    if hasattr(model_obj, "dict"):
        return model_obj.dict()  # pydantic v1
    raise TypeError("Unsupported model object for serialization")


def _create_timestamped_output_dir(base_dir: Path = Path("outputs")) -> Path:
    base = base_dir.resolve()
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    run_dir = base / stamp
    suffix = 1
    while run_dir.exists():
        run_dir = base / f"{stamp}_{suffix}"
        suffix += 1
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _target_in_run_dir(run_dir: Path, requested_path: str) -> Path:
    return run_dir / Path(requested_path).name


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Run OCR pipeline and export structured outputs.")
    parser.add_argument("--image", required=True, help="Input image path")
    parser.add_argument(
        "--ocr-provider",
        default=_resolve_ocr_provider_default(),
        choices=["local_hwdb", "baidu"],
        help=(
            "OCR backend (default from CALLIGRAPHY_OCR_PROVIDER/OCR_PROVIDER, "
            "fallback baidu)"
        ),
    )

    # Local OCR args
    parser.add_argument("--local-model-name", default="ResNet", choices=["LeNet", "VGG", "ResNet"])
    parser.add_argument("--local-model-path", default=None, help="Optional custom model.pth path")
    parser.add_argument("--local-char-dict-path", default=None, help="Optional custom char_dict path")
    parser.add_argument("--local-use-cuda", action="store_true", help="Use CUDA for local OCR if available")

    # Baidu OCR args
    parser.add_argument("--baidu-api-key", default=None)
    parser.add_argument("--baidu-secret-key", default=None)

    # Match/DB args
    parser.add_argument("--disable-db-match", action="store_true", help="Only run OCR and skip DB matching")
    parser.add_argument("--db-path", default=None, help="Optional custom database path")
    parser.add_argument("--sample-limit-per-char", type=int, default=120)
    parser.add_argument(
        "--feature-prefilter-limit",
        type=int,
        default=40,
        help="Use lightweight feature prefilter before expensive CV scoring",
    )
    parser.add_argument("--top-k-per-char", type=int, default=5)
    parser.add_argument("--top-n-authors", type=int, default=5)
    parser.add_argument("--min-score-to-vote", type=float, default=45.0)
    parser.add_argument(
        "--import-style-scores",
        action="store_true",
        help="Import style-score markdown table into DB before report generation",
    )
    parser.add_argument(
        "--style-score-markdown",
        default=str(Path(__file__).resolve().parent / "instance" / "书法作品打分.md"),
        help="Markdown file path for style score import",
    )

    # Output
    parser.add_argument("--out", default="outputs/match_bundle.json", help="Output path for MatchBundle JSON")
    parser.add_argument("--with-basic-report", action="store_true", help="Also generate basic report JSON")
    parser.add_argument("--report-out", default="outputs/basic_report.json", help="Output path for basic report JSON")
    parser.add_argument(
        "--web-report-out",
        default="outputs/report.html",
        help="Output path for readable HTML report",
    )
    parser.add_argument(
        "--no-web-report",
        action="store_true",
        help="Skip HTML report rendering",
    )
    parser.add_argument(
        "--hybrid-llm-report",
        action="store_true",
        help="生成规则报告 + 雷达图 + 基于八维的 LLM 评语（密钥见 --openai-api-key / llm_config 硬编码 / 环境变量）",
    )
    parser.add_argument(
        "--llm-commentary",
        action="store_true",
        help="与 --hybrid-llm-report 相同效果：附加 LLM 评语（可单独使用，需同时产出报告）",
    )
    parser.add_argument(
        "--no-radar",
        action="store_true",
        help="不生成八维雷达图 PNG",
    )
    parser.add_argument(
        "--radar-out",
        default="outputs/style_radar.png",
        help="雷达图输出路径（默认 outputs/style_radar.png）",
    )
    parser.add_argument("--openai-api-key", default=None, help="Override OPENAI_API_KEY for hybrid report")
    parser.add_argument(
        "--openai-base-url",
        default=None,
        help="Override OPENAI_BASE_URL (default https://api.openai.com/v1)",
    )
    parser.add_argument("--openai-model", default=None, help="Override OPENAI_MODEL (default gpt-4o-mini)")
    args = parser.parse_args(argv)
    run_dir = _create_timestamped_output_dir()
    print(f"Run output directory: {run_dir}")

    bundle = ocr_to_match_bundle(
        image_path=args.image,
        ocr_provider=args.ocr_provider,
        baidu_api_key=args.baidu_api_key,
        baidu_secret_key=args.baidu_secret_key,
        local_model_name=args.local_model_name,
        local_model_path=args.local_model_path,
        local_char_dict_path=args.local_char_dict_path,
        local_use_cuda=args.local_use_cuda,
        with_db_match=not args.disable_db_match,
        sample_limit_per_char=args.sample_limit_per_char,
        feature_prefilter_limit=args.feature_prefilter_limit,
        top_k_per_char=args.top_k_per_char,
        top_n_authors=args.top_n_authors,
        min_score_to_vote=args.min_score_to_vote,
        db_path=args.db_path,
    )

    out_path = _target_in_run_dir(run_dir, args.out)
    out_path.write_text(json.dumps(_model_to_dict(bundle), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Match bundle saved: {out_path}")

    if args.with_basic_report or args.hybrid_llm_report or args.llm_commentary:
        if args.import_style_scores:
            imported = import_style_scores(Path(args.style_score_markdown), db_path=args.db_path)
            print(f"Style score rows imported: {imported}")
        radar_out = None if args.no_radar else str(_target_in_run_dir(run_dir, args.radar_out))
        llm_on = bool(args.hybrid_llm_report or args.llm_commentary)
        report = generate_complete_style_report(
            bundle,
            radar_out=radar_out,
            skip_radar=args.no_radar,
            llm_commentary=llm_on,
            openai_api_key=args.openai_api_key,
            openai_base_url=args.openai_base_url,
            openai_model=args.openai_model,
        )
        report_path = _target_in_run_dir(run_dir, args.report_out)
        report_path.write_text(json.dumps(_model_to_dict(report), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Report saved: {report_path}")
        if not args.no_web_report:
            web_out = render_style_report_html(report, _target_in_run_dir(run_dir, args.web_report_out))
            print(f"Web report saved: {web_out}")


if __name__ == "__main__":
    main()

