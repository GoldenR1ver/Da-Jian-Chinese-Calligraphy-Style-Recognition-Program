# report_generator — 风格报告生成

## 作用

将 `MatchBundle`（含逐字候选与相似度）整理为**结构化报告**。纯规则版本（不依赖 LLM）可输出：

1. 书法八维雷达图
2. 总体最相似书法家 Top5
3. 单字最相似书法家 Top1（逐字）
4. 基于八维的规则总评
5. 基于当前风格的相似书法家推荐

并可选叠加 OpenAI 兼容 API 中文评语。

## 主要内容

| 文件 / 目录 | 说明 |
|-------------|------|
| `schema.py` | `StyleReport`、`ReportEvidenceItem`、`ReportStyleDimension` |
| `basic_report.py` | `generate_basic_report`：权重聚合、八维、摘要 |
| `style_math.py` | 候选相似度累加、`weighted_user_eight_dimensions` |
| `radar_chart.py` | `render_eight_dim_radar`（八维极坐标图） |
| `web_report.py` | `render_style_report_html`：可读 HTML 报告（可直接浏览器打开） |
| `complete_report.py` | `generate_complete_style_report`：规则层 + 雷达 + 可选 LLM |
| `commentary_llm.py` | `attach_llm_commentary`，提示词 `prompts/commentary_zh_v2.txt` |
| `llm_client.py` | OpenAI 兼容 `chat/completions` 调用 |
| `llm_config.py` | 可选硬编码密钥；`resolve_*` 与 CLI 参数、环境变量优先级 |

## 八维说明

与数据库 `author_style_scores` 一致：**中和、端庄、典雅、古朴、刚劲、险峻、洒脱、妍美**。仅当书家在库中八列数值齐全时参与加权。

## 使用方式

```python
from src.report_generator import generate_basic_report, generate_complete_style_report

# 仅规则报告
report = generate_basic_report(bundle)

# 报告 + 雷达 + LLM（需密钥）
report = generate_complete_style_report(
    bundle,
    radar_out="outputs/radar.png",
    llm_commentary=True,
    openai_api_key="sk-...",
)
```

命令行见 [项目根 README](../../README.md)。

一键网页报告（默认开启）：

```bash
python -m src.pipeline --image <图片> --with-basic-report --report-out outputs/report.json --web-report-out outputs/report.html
```

未来若开启 LLM，`meta.llm_commentary` 会自动进入 HTML 的「LLM 扩展分析」区块，无需改模板。

## 测试

- `tests/test_llm_report_fallback.py`：无 API 密钥时 LLM 降级路径。
- 规则报告与 `StyleReport` schema 的更多用例可在 `tests/` 中扩展。

```bash
pip install -r requirements.txt
python -m pytest tests -q
```

## 开源感谢

- 感谢 `matplotlib` 支撑八维雷达图绘制，`pydantic` 提供结构化报告模型。
- 感谢 OpenAI 兼容 API 生态，为后续可插拔的 LLM 扩展分析提供接口标准。
