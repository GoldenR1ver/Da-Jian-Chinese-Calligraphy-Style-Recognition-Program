# 大见 · 书法风格识别

命令行程序。给它一幅书法图片和释文，它会切出单字、清洗后写入自己的数据库；再拿另一幅作品来比对，估计更接近哪位作者的哪种风格。

没有网页界面。入口：

```bash
python -m calligraphy_style --help
```

## 代码布局

逻辑集中在 `calligraphy_style/`：

| 文件 | 职责 |
| --- | --- |
| `cli.py` | 命令行 |
| `db.py` | 建表、作者、变体、评分、样本 |
| `seed.py` | 默认库里的维度、作者别名、繁体/异体对照 |
| `images.py` | 切字与清洗 |
| `ingest.py` | 固定的作品导入流程 |
| `analyze.py` | 和字库比对，汇总作者与八维 |
| `ocr.py` | 可选：用百度 OCR 给切块贴字，代替手工释文 |

依赖写在 `requirements.txt`：OpenCV、NumPy、scikit-image、requests。

```bash
pip install -r requirements.txt
```

## 数据库

默认文件是 `data/calligraphy.db`，已经带好表和基础数据，可以直接导入作品。路径可用 `--db` 或环境变量 `CALLIGRAPHY_DB_PATH` 换掉。

一条样本沿着这张链存放：

```text
单字（规范字）
  └─ 变体（书写形：标准形、繁体、异体）
       └─ 单字图
作者
  └─ 作者风格（如「颜真卿 / 楷书」）
       └─ 八维评分
       └─ 作品
            └─ 单字图
```

八维顺序固定为：中和、端庄、典雅、古朴、刚劲、险峻、洒脱、妍美。分数由你写入，范围 0–100。

默认库里有：

- 这八个维度的名称
- 五种常见书体：楷书、行书、草书、隶书、篆书（导入时也可以用别的风格名）
- 八位作者和一批别名（例如「多宝塔」会归到颜真卿，「文征明」归到文徵明）
- 约一百组繁体/异体到简体规范字的对照（例如「爲」归到「为」）

里面没有单字图片。图片只来自下面的导入流程。缺的作者、风格、变体可以随后用命令补上。

重建或补齐这个文件：

```bash
python -m calligraphy_style init
python -m calligraphy_style status
```

`init` 不会删掉已经导入的作品。

## 导入一幅作品

流程是固定的，每次导入都走同一条：

1. 读入整页，统一成浅底；红色印章尽量涂成背景。
2. 去噪、二值化，按轮廓切出单字，并合并重叠的笔画碎片。
3. 按版式排序。`horizontal` 是横写，行从上到下、字从左到右。`vertical` 是竖写，列从右到左、字从上到下。
4. 用释文里的汉字按这个顺序贴标签。标点、空格、换行会跳过。字块数和汉字数不一致就整幅放弃，不写半幅。
5. 每个字再清洗一次：去掉碎点、收紧到笔画、放到 128×128 的白底上，黑字居中。
6. 书写形如果已在变体表里，就挂到对应规范字；否则这个字自己成为规范字。
7. 写入作者、风格、作品和单字图。

```powershell
python -m calligraphy_style import `
  --image D:\works\duobao.png `
  --author 颜真卿 `
  --style 楷书 `
  --title 多宝塔局部 `
  --text "唐故通议大夫" `
  --layout horizontal `
  --debug-dir outputs\debug
```

`--debug-dir` 会把切出来的单字图存下来，方便核对顺序。竖幅加上 `--layout vertical`。

没有释文时，可以改用百度高精度 OCR 给切块贴字。它不负责切字，只和本地切块对位置：

```bash
$env:BAIDU_OCR_API_KEY = "<API Key>"
$env:BAIDU_OCR_SECRET_KEY = "<Secret Key>"
python -m calligraphy_style import --image D:\works\a.png --author 米芾 --style 行书 --ocr baidu
```

字与字之间需要留出空隙。连笔、印章压住的字、深色花哨背景会切错；切错时看调试图，改版式或改成手工释文后再导。

补一条变体，或从表格批量导入（列是「规范字,书写形,类型」，类型为 `traditional`、`variant`、`simplified`、`standard`）：

```bash
python -m calligraphy_style variant add --canonical 为 --form 爲 --type variant
python -m calligraphy_style variant import --file variants.csv
```

给某个作者风格打八维分：

```bash
python -m calligraphy_style score --author 颜真卿 --style 楷书 --scores 60,70,65,55,80,40,50,45
```

## 比对一幅新作品

切字、清洗、贴标签的方式和导入相同，然后在同一规范字的样本里做比对。先用字形特征缩小范围，再用结构相似和模板匹配打 0–100 分。每个字只把票投给一位作者风格，低于 45 分不投票。已有评分的风格会按相似度加权，得到这幅字的八维。

```bash
python -m calligraphy_style analyze --image D:\mine\practice.png --text "唐故通议" --layout horizontal --out outputs\report.json
```

终端会打印接近的作者风格、八维和逐字结果。`--out` 另存一份 JSON。
