# OCR Recognizer

在本仓库中的位置：**流水线第一步**——把用户图片解析为「行 / 单字 + 位置」，供 `src.pipeline` 组装 `MatchBundle`，再进入字库匹配与报告。

本目录提供两种识别方式：**百度 OCR（云端）**与**本地 HWDB 模型**（见 `local_hwdb.py`）。二者在流水线中通过 `--ocr-provider` 切换。
当前 `src.pipeline` 的默认值为 **baidu**（可通过环境变量快速切换，见下）。

- 总览与命令行：[项目根 README](../../README.md)
- 测试说明：[tests/README.md](../../tests/README.md)

## 百度 OCR 使用前准备

1. 在 [百度智能云](https://console.bce.baidu.com/) 创建应用，开通「通用文字识别」中的 **高精度版**（与代码中的 `accurate` 接口对应）。
2. 记下 **API Key** 与 **Secret Key**，不要提交到仓库；建议使用环境变量。

## 环境变量（推荐）

```text
BAIDU_OCR_API_KEY=<你的 API Key>
BAIDU_OCR_SECRET_KEY=<你的 Secret Key>
```

PowerShell 示例（当前会话有效）：

```powershell
$env:BAIDU_OCR_API_KEY = "你的API_KEY"
$env:BAIDU_OCR_SECRET_KEY = "你的SECRET_KEY"
```

## 用法

### 1. 仅调用 OCR 模块（输出解析后的 JSON）

在项目根目录执行：

```powershell
python -m src.ocr_recognizer.ocr "路径\到\图片.jpg"
```

若未设置环境变量，可显式传入：

```powershell
python -m src.ocr_recognizer.ocr "路径\到\图片.jpg" --api-key <API_KEY> --secret-key <SECRET_KEY>
```

成功时标准输出为 `parse_ocr_result` 的结果：每行文字、行框与单字位置等。若返回中包含 `error_code` / `error_msg`，请对照百度文档检查密钥、接口开通与配额。

### 2. 走完整流水线（生成 `MatchBundle` JSON）

```powershell
python -m src.pipeline --image "路径\到\图片.jpg" --ocr-provider baidu --baidu-api-key <API_KEY> --baidu-secret-key <SECRET_KEY>
```

默认输出：`outputs/match_bundle.json`。

### 3. 快速切换默认 OCR（对 `python -m src.pipeline` 生效）

优先级：`--ocr-provider` > `CALLIGRAPHY_OCR_PROVIDER` / `OCR_PROVIDER` > 内置默认 `baidu`。

```powershell
# 默认改成本地模型
$env:CALLIGRAPHY_OCR_PROVIDER = "local_hwdb"

# 默认改回百度 OCR
$env:CALLIGRAPHY_OCR_PROVIDER = "baidu"
```

## 测试

### 离线单元测试（不访问百度）

解析逻辑由 `parse_ocr_result` 处理，仓库内已有用例：

```powershell
pytest tests/test_ocr_parse.py -v
```

### 联网冒烟测试

1. 配置好 API Key / Secret Key（环境变量或命令行参数）。
2. 准备一张清晰的中文图像（如 `res/example/` 下示例）。
3. 运行「用法 1」中的命令；能打印出含 `line_text`、`chars` 的 JSON 即表示鉴权与接口调用正常。

## 实现说明

- `ocr.py`：OAuth 获取 `access_token`，调用高精度通用文字识别接口，并将结果解析为行/字结构。
- `local_hwdb.py`：本地模型识别，接口形状与解析流程兼容同一套 `parse_ocr_result`（在 `ocr_provider=local_hwdb` 时使用）。

## 开源感谢

- 感谢百度 OCR 提供中文识别能力与开放接口文档。
- 感谢 `requests`、`opencv-python` 等开源项目支撑 OCR 调用与图像处理。
