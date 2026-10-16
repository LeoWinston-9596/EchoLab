# EchoLab

**把英文视频变成可以逐句听、跟读和复习的学习材料。**

Video-to-learning pipeline · Bilingual subtitles · Shadowing player · Source-validated vocabulary cards

EchoLab 是一个在自己电脑上运行的英语学习工具。导入视频、音频或在线链接后，它会整理出按语义切分的中英字幕、IPA 音标，以及来自原文的单词和语块卡片，再交给浏览器播放器进行单句循环、听后复述和影子跟读。

它最初是为家人做的：学习者打开素材库就能练习，安装和配置留给维护者处理。项目由 Python 处理流水线和 HTML/JavaScript 学习界面组成；语音识别在本机运行，翻译与知识点提取调用 LLM API。

[快速开始](#快速开始) · [导入素材](#导入素材) · [实现方式](#实现方式) · [限制与数据说明](#限制与数据说明) · [开发与维护](#开发与维护)

## 学习时能做什么

| 功能 | 使用方式 |
| --- | --- |
| 按语义练习 | 字幕按适合复述的语义群组织，点击一句回到对应片段 |
| 单句循环与暂停 | 重听同一句，或播完一句自动停下，再凭记忆复述 |
| 调整字幕与语速 | 切换中英字幕，降低播放速度，逐步过渡到原速跟读 |
| 单词与语块卡片 | 同时学习生词、短语、搭配和口语句式 |
| 回原句学习 | 从卡片跳回视频中的出处，而不是只背脱离语境的释义 |
| 素材库与收藏 | 浏览已处理素材，保存句子、词条和学习进度 |

卡片包括六类：单词、短语、短语动词、搭配、口语句式、话语标记。后五类都是多词表达，例如把 `on the same page` 作为一个表达学习，而不是拆成几个孤立单词。

给只需要使用播放器的家人，请看 [家人使用说明](家人使用说明.md)。

## 快速开始

需要 **Python 3.10 或更新版本**。以下命令均在项目根目录执行。

### 1. 安装依赖

```bash
git clone https://github.com/LeoWinston-9596/EchoLab.git
cd EchoLab
python -m venv .venv
```

激活虚拟环境：

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

```bash
python -m pip install -r requirements.txt
```

按需要安装额外工具：

| 工具 | 什么时候需要 |
| --- | --- |
| `yt-dlp` | 获取 YouTube 字幕，以及解析 TikTok、抖音、Bilibili 等平台链接 |
| `espeak-ng` | 合成演示音频、生成句子 IPA，以及在本地补充词条音标 |
| `ffmpeg` | 推荐安装，用于音频转换和封面生成；缺少时，本地识别可尝试 PyAV 解码支持的格式 |

```bash
python -m pip install -U yt-dlp
```

Windows 可使用：

```powershell
winget install Gyan.FFmpeg
winget install eSpeak-NG.eSpeak-NG
```

安装外部程序后，重新打开终端并激活虚拟环境。macOS / Linux 可通过系统包管理器安装 `ffmpeg` 和 `espeak-ng`。

### 2. 先体验，不调用模型 API

安装 `espeak-ng` 后：

```bash
python demo.py
python serve.py
```

服务会打开播放器；素材库位于 **http://localhost:8777/library.html**。

演示使用内置文本和本机合成音频，不需要 API Key，也不下载语音识别模型。它用于体验学习流程，不代表真实视频的识别质量。演示时无需启动队列处理。

### 3. 配置模型服务

复制 `.env.example` 为 `.env`，填入你要使用的服务密钥：

```dotenv
DEEPSEEK_API_KEY=your_deepseek_api_key
# 使用 --llm kimi 时配置：
# MOONSHOT_API_KEY=your_moonshot_api_key
```

默认使用 DeepSeek；通过 `--llm kimi` 切换到 Kimi。处理本地音视频时，首次运行 ASR 会下载模型；耗时取决于网络、模型大小、素材长度和电脑性能。

## 导入素材

### 本地视频或音频

```bash
python process.py "path/to/video.mp4" --title "咖啡店点单"
python serve.py
```

结果写入 `library/<素材编号>/`，包含播放器读取的 `data.json`，以及适用时的媒体文件和封面。

### 在线链接

```bash
# 先检查链接能解析出什么
python fetch.py "https://example.com/video"

# 处理素材；将 VIDEO_ID 换成真实视频 ID
python process.py --url "https://www.youtube.com/watch?v=VIDEO_ID" --title "一期访谈"
```

| 来源 | 处理路径 | 注意事项 |
| --- | --- | --- |
| YouTube | 优先获取已有英文字幕，并嵌入 YouTube 播放器 | 优先人工字幕，再尝试自动字幕；取不到字幕时默认尝试下载并识别 |
| TikTok / 抖音 / Bilibili | 获取媒体后运行识别流水线 | 依赖 `yt-dlp`，可能受平台变化、地区和访问限制影响 |
| 其他网址 | 尝试媒体直链、播客订阅源、页面媒体地址或 HLS | 不保证任意网页都能解析 |

只希望 YouTube 使用字幕、不自动切换到下载识别，可加 `--no-fallback`。要主动走下载识别路径，可加 `--force-download`。嵌入播放仍然需要联网。

### 用书签加入队列

1. 运行 `python serve.py`。
2. 打开 **http://localhost:8777/setup**，将页面上的书签按钮拖到浏览器书签栏。
3. 在视频页面点击书签，将链接送入本地队列。
4. 在另一个已激活虚拟环境的终端运行 `python worker.py --watch`，处理队列中的链接。
5. 处理完成后，刷新素材库开始学习。

网页服务与队列处理需要分别保持运行。浏览器若拦截书签请求，会尝试新标签页方式。更换电脑后需要重新安装书签。

## 实现方式

```text
本地文件 / 在线媒体 → 词级时间戳 ASR ─┐
                                     ├→ 语义群切分与翻译 → IPA → data.json → 学习播放器
YouTube 字幕 ─────→ 词序列与时间轴 ──┘          │
                                               └→ 知识点提取 → 来源校验 → 卡片
```

**用词下标连接模型输出与原始时间轴。** 语义切分阶段让模型返回起止词下标与中文翻译，英文文本和时间信息从源词序列重建。程序检查并修复区间覆盖、遗漏与重叠，避免模型改写原文后难以定位。但最终同步精度仍受 ASR 或源字幕时间戳质量影响。

**生成卡片后，再检查表达是否来自原文。** 校验考虑常见词形变化及短语动词的分离形式，例如将 `take off` 与 `took it off` 匹配。不通过的词条会被剔除并记录。这是对来源的检查，不是对释义、例句和翻译正确性的完整证明。

**把可重复计算的结果留在本机。** LLM 请求按提供方及请求内容缓存；已有请求可以复用，但换模型、提示词或参数后仍可能产生新的 API 调用。IPA 通过本机 `espeak-ng` 生成，不依赖付费音标服务。

**把获取、处理和学习分开。** `process.py` 可以单独运行；`worker.py` 读取队列并启动处理子进程，`serve.py` 提供网页。播放器读取生成的 JSON，本地媒体服务支持 Range 请求，便于跳转到具体片段。

## 限制与数据说明

- **不是完全离线工具。** 本地 ASR 不调用付费识别 API，但首次下载模型需要网络；切分、翻译和卡片生成会把相关转写文本发送给所选 LLM 服务。不要导入不适合发送给该服务的内容。
- **不承诺固定准确率。** 口音、背景音、多人重叠说话及源字幕错误都会影响结果。低置信度词和被剔除卡片记录在 `data.json` 的 `review` 字段，便于校对；这不覆盖所有错误。
- **费用以实际调用为准。** 运行结束会输出用量和费用估算，但代码内单价可能滞后。`--no-cards` 跳过卡片提取，其他模型调用仍会发生。
- **音标与考级标签需要判断。** 本地 IPA 生成不等同于真实语流的连读标注。`wordlists/` 中的词表优先于模型标签，但标签质量取决于词表本身。
- **学习状态保存在当前浏览器。** 收藏和进度使用浏览器本地存储，不会自动跨设备同步；清除浏览器数据可能丢失这些状态。
- **面向本机与可信局域网。** 服务默认监听 `0.0.0.0:8777`，方便同一 Wi-Fi 下的设备访问；它不是带完整账户隔离的公网服务。API Key 放在 `.env` 中，不应提交到仓库。
- **平台链接可能失败。** 使用自己有权处理的内容，遵守来源平台条款；项目不提供绕过付费墙或 DRM 的功能。

## 开发与维护

### 常用选项

| 参数 | 用途 |
| --- | --- |
| `--llm deepseek` / `--llm kimi` | 选择模型服务 |
| `--llm-model NAME` | 覆盖该服务的默认模型 |
| `--asr-model base.en` | 选择 ASR 模型；默认 `small.en`，可按速度与质量需求调整 |
| `--no-cards` | 跳过知识点卡片提取 |
| `--no-cache` | 不复用 LLM 请求缓存 |
| `--no-fallback` | YouTube 字幕获取失败时停止，不尝试下载识别 |

完整参数见 `python process.py --help`。`--keep-media` 只记录原文件位置而不复制媒体，可能受到浏览器对 `file://` 的限制，不建议作为默认使用方式。

### 运行队列

```bash
python worker.py --watch          # 持续处理新加入的链接
python worker.py --retry-failed   # 将失败条目重新纳入处理
```

不想使用队列时，直接运行 `python process.py` 处理单个文件或链接即可。

### 代码导航

| 位置 | 职责 |
| --- | --- |
| `process.py` | 处理入口，组织识别、生成、校验和保存 |
| `serve.py`、`worker.py` | 网页服务与后台队列 |
| `library.html`、`player.html` | 素材库与学习界面 |
| `teco/asr.py`、`teco/captions.py` | 本地转写与 YouTube 字幕解析 |
| `teco/segment.py`、`teco/cards.py` | 语义群切分、翻译及卡片来源校验 |
| `teco/llm.py`、`teco/ipa.py` | 模型调用、缓存、用量统计及音标 |
| `teco/platforms.py`、`teco/ingest.py`、`teco/inbox.py` | 来源识别、链接获取、去重与入队 |
| `tests/test_ingest.py` | 链接解析相关测试 |

### 检查链接解析逻辑

```bash
python tests/test_ingest.py
```

测试用于检查程序逻辑，不代表对识别、翻译或学习效果做过完整评测。

在线视频接入的背景与取舍见 [探索笔记](docs/在线视频解析-探索笔记.md)。
