# character_matcher — 字库匹配与检索

## 作用

在流水线中承接 OCR 输出的单字与位置，从本地 SQLite 字库（`characters` 表）中检索**同字**样本，计算与用户字图的相似度，填充 `MatchBundle` 中的逐字候选与书家聚合信息。

## 主要内容

| 文件 | 说明 |
|------|------|
| `schema.py` | `MatchBundle`、`SingleCharMatch`、`GlyphCandidate`、`AuthorAttribution` 等结构化模型 |
| `repository.py` | 数据库连接、`characters` 查询、`author_style_scores` / `author_alias`、八维键名 |
| `matcher.py` | `enrich_bundle_with_db_matches`：裁字 → 特征预筛选 → `combined_similarity` 精排 → Top-K 候选与作者列表（作者聚合采用「单字去重投票 + 置信度加权」） |
| `feature_index.py` | 轻量特征（Hu 矩 + 投影）、`glyph_features` 表缓存、预筛选排序 |

## 依赖

- 默认数据库路径：`src/instance/Kop_Date.db`（可用环境变量 `CALLIGRAPHY_DB_PATH` / `KOP_DATE_DB_PATH` 覆盖）。
- 相似度计算依赖 `style_analyzer` 中的 `combined_similarity`；SVG 样本栅格化可选 `cairosvg`（见 `src/instance/README.md`）。
- 默认 `min_score_to_vote=45`，低于阈值的候选不参与作者投票；每个识别字仅为一个作者投票，减少同风格作者串票。

## 使用方式

一般不单独调用，由 `src.pipeline` 在 `ocr_to_match_bundle(..., with_db_match=True)` 时自动执行。

编程接口示例：

```python
from src.character_matcher import MatcherConfig, enrich_bundle_with_db_matches
from src.character_matcher.schema import MatchBundle

bundle = MatchBundle(version="0.1.0", image_path="x.png", ocr_engine="test", chars=[], authors=[])
bundle = enrich_bundle_with_db_matches(bundle, MatcherConfig(db_path=None))
```

## 测试

本模块逻辑由根目录 `tests/` 中间接覆盖（pipeline 打桩与端到端需真实图 + 数据库）。新增单元测试时可使用小型 fixture `.db` 与 `pytest`。

详见 [项目根 README](../../README.md#测试) 与 [instance/README.md](../instance/README.md)。

## 开源感谢

- 感谢 `opencv-python`、`numpy`、`sqlite3` 等开源生态提供图像处理与数据存储基础能力。
- 感谢中文书法数据集贡献者，为匹配评估提供了可复用样本来源。
