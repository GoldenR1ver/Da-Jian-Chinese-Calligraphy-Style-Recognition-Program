# `src/` 源码说明

本目录为「大见」书法风格识别程序的核心代码，按流水线从 **图像 → OCR → 字库匹配 → 风格报告** 组织。

## 模块一览

| 目录 / 文件 | 说明 | 详细文档 |
|-------------|------|----------|
| `pipeline.py` | 主入口：OCR、`MatchBundle`、可选完整报告 | 根目录 [README.md](../README.md) |
| `ocr_recognizer/` | 百度高精度 OCR / 本地 HWDB 适配 | [ocr_recognizer/README.md](ocr_recognizer/README.md) |
| `character_recognizer/` | 离线手写单字分类（HWDB，可选） | [character_recognizer/README.md](character_recognizer/README.md) |
| `character_matcher/` | 字库检索、相似度、特征预筛选 | [character_matcher/README.md](character_matcher/README.md) |
| `style_analyzer/` | 字形预处理与 CV 相似度基线 | [style_analyzer/README.md](style_analyzer/README.md) |
| `report_generator/` | 八维报告、雷达图、LLM 评语 | [report_generator/README.md](report_generator/README.md) |
| `instance/` | SQLite 数据库、评分表导入、特征缓存 | [instance/README.md](instance/README.md) |

## 运行方式

在仓库根目录执行（Windows / Linux 均可）：

```bash
python -m src.pipeline --image <图片路径> --with-basic-report
```

更多参数见根目录 [README.md](../README.md)。

## 开源感谢

- 感谢 Python、NumPy、OpenCV、Matplotlib、PyTorch 等开源项目共同构成项目基础能力。
- 感谢 CAOD 与同济中文书法数据集等开放数据资源推动中文书法 AI 研究。
