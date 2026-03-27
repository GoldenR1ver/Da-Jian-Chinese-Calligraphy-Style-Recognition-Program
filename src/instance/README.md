# instance — 数据与数据库

## 作用

存放默认 SQLite 字库、书法八维评分表 Markdown、作者别名规则，以及将评分与别名**导入数据库**的脚本；可选离线构建字形轻量特征缓存。

## 文件与表

| 文件 | 说明 |
|------|------|
| `Kop_Date.db` | 默认数据库（勿随意移动；可用环境变量指向副本） |
| `书法作品打分.md` | 书家八维人工评分表（导入至 `author_style_scores`） |
| `author_alias_rules.txt` | 手写别名规则：`别名|标准名` |
| `author_alias_rules.example.txt` | 示例 |

核心表（与风格匹配相关）：

- **`characters`**：单字样本，`character`、`author_name`、`style`、`svg` / `image_data` 等。
- **`author_style_scores`**（可由脚本创建）：八维分数与 `author_name`。
- **`author_alias`**：别名 → 标准名。
- **`glyph_features`**（可选）：由 `build_feature_cache` 写入的预计算特征。

其余表（`user`、`post` 等）多来自原 Web 项目，离线脚本可忽略。

## 环境变量

| 变量 | 含义 |
|------|------|
| `CALLIGRAPHY_DB_PATH` / `KOP_DATE_DB_PATH` | 覆盖默认 `Kop_Date.db` 路径 |

Python 中获取路径：

```python
from src.instance import get_kop_date_db_path
print(get_kop_date_db_path())
```

## 常用命令

```bash
# 将评分表 Markdown 导入 author_style_scores
python -m src.instance.style_score_importer

# 作者别名（前缀启发式 + 规则文件）
python -m src.instance.author_alias_importer

# 仅手写规则文件
python -m src.instance.author_alias_importer --rules-file src/instance/author_alias_rules.txt --skip-prefix-heuristic

# 离线预计算 glyph_features（需 SVG 栅格化能力，见下）
python -m src.instance.build_feature_cache

# 导入同济单字数据集（style-author/char/*.gif）
python -m src.instance.tongji_importer --dataset-root res/chinese-calligraphy-dataset/chinese-calligraphy-dataset-with-calligrapher
```

若 `build_feature_cache` 大量 `failed (no raster)`，请安装 `cairosvg`，并确保 Python 的 `xml`/`pyexpat` 可用（个别 Anaconda 环境需修复）。

## 命令行排查数据库

```bash
sqlite3 src/instance/Kop_Date.db ".tables"
sqlite3 src/instance/Kop_Date.db ".schema characters"
```

## 字库设计扩展（参考）

若后续扩展字段（朝代、来源、质量、许可等），可新表或迁移 `characters` 元数据；图片大库建议**路径 + 外置文件**，避免 SQLite 体积膨胀。详见项目根 README 中的路线图说明。

## 测试

导入脚本与数据库路径可被 `pytest` 使用小型 fixture 库覆盖；当前以根目录 `tests/` 为主。

## 开源感谢

- 感谢 SQLite 官方与 Python 标准库提供轻量稳定的数据持久化能力。
- 感谢 CAOD、同济中文书法数据集等开源/开放数据项目，为字库扩展提供数据基础。
