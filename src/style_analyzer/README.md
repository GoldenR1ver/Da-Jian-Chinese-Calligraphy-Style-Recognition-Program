# style_analyzer — 字形分析与相似度基线

## 作用

提供图像预处理、轮廓提取、以及 **SIFT + 模板匹配 + SSIM** 等经典 CV 相似度，供 `character_matcher` 在字库样本与用户裁字之间做 **精排**（`combined_similarity`）。

## 主要内容

| 文件 | 说明 |
|------|------|
| `fonts_comparison.py` | `combined_similarity`：两幅图路径 → 多指标综合分（0–100） |
| `contour.py` | `extract_text_contours`：轮廓提取与透明背景输出 |
| `single_char.py` | 第三方网站字形 SVG 抓取（Playwright，可选工具） |
| `great_works.py` | 作品检索脚本（Playwright，可选工具） |

## 依赖

- `opencv-python`、`numpy`、`scikit-image`（见根目录 `requirements.txt`）。
- 爬虫类脚本需 `playwright`；若不用可忽略。

## 使用方式

由 `character_matcher.matcher` 在匹配阶段调用；也可单独调试：

```python
from src.style_analyzer import combined_similarity
sift, tmpl, ssim, total = combined_similarity("user.png", "ref.png")
```

## 测试

本目录暂无独立 `pytest` 用例；回归依赖根目录 `tests/` 与手工对比两张图。添加新测试时建议对 `combined_similarity` 使用固定小图 fixture。

详见 [项目根 README](../../README.md#测试)。

## 开源感谢

- 感谢 `opencv-python`、`scikit-image`、`numpy` 提供经典 CV 算法与数值计算能力。
- 感谢 Playwright 社区生态支持可选的数据抓取与页面自动化工具链。
