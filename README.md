# lzp-video-subtitle

`lzp-video-subtitle` 是一个本地中文字幕生成 skill。

它的目标很简单：

```text
给视频 / 音频生成中文字幕
输出 final.srt / final.txt / review_focus.csv
把人工修正沉淀成长期可复用的词库 profile
```

默认使用本地 Qwen ASR 模型，不把视频上传到云端。

---

## 一句话流程

```text
/lzp-video-subtitle
→ 检查本机环境
→ 如有缺失，经确认后补齐
→ 用本地样本 smoke-test
→ 正式生成字幕
→ 人工检查
→ learn 学习人工修正
```

用户主要只需要记住一个入口：

```text
/lzp-video-subtitle
```

底层的 `healthcheck / setup-plan / setup / smoke-test / run / batch / learn` 是 agent 内部能力，普通用户不需要逐个记忆。

---

## 产品原则

### 最小安装

安装 skill 本体时，不会自动下载模型，也不会自动安装一堆依赖。

首次使用时只做只读检查：

```text
healthcheck → setup-plan
```

只有发现缺失项，并且用户确认后，才执行：

```text
setup
```

### 优先复用已有环境

如果机器上已经有可用的 Qwen Python 环境，不要重复安装，直接用 `--python` 指定：

```powershell
python scripts/video_subtitle_cli.py smoke-test --python "D:\WorkBuddy_Local\qwen_local_3060_pilot\.venv\Scripts\python.exe" --input "C:\path\sample.mp4"
```

如果已有模型目录，也可以复用：

```powershell
$env:VIDEO_SUBTITLE_MODELS_DIR = "D:\WorkBuddy_Local\qwen_local_3060_pilot\models"
```

### 非核心指标不阻断主流程

`ffprobe` 可以让 `sample_duration / rtf` 统计更完整，但它不是字幕生成的阻断依赖。

如果 `ffprobe` 不可用，CLI 会尝试用 `ffmpeg -i` fallback。即使最终拿不到时长，只要字幕三件套生成成功，主链路仍算成功；报告会在 `warnings` 里说明原因。

---

## 运行环境位置

默认 runtime home：

```text
Windows: %LOCALAPPDATA%\lzp-video-subtitle
macOS/Linux: ~/.local/share/lzp-video-subtitle
```

默认 Qwen Python 环境：

```text
<runtime_home>/envs/qwen-local
```

默认模型目录：

```text
<runtime_home>/models/qwen
```

可用环境变量覆盖 runtime home：

```text
LZP_VIDEO_SUBTITLE_HOME
VIDEO_SUBTITLE_HOME
```

可用环境变量覆盖模型目录：

```text
VIDEO_SUBTITLE_MODELS_DIR
LZP_VIDEO_SUBTITLE_MODELS_DIR
QWEN_SUBTITLE_MODELS
```

---

## 你会得到什么

每个视频默认生成三件套：

```text
final.srt          字幕文件
final.txt          纯文本稿
review_focus.csv   建议人工重点检查的位置
```

默认输出到视频旁边：

```text
<input_video_dir>/<video_basename>_subtitle/
```

例如：

```text
C:\Users\Lin\Videos\lesson01.mp4
→ C:\Users\Lin\Videos\lesson01_subtitle\
```

批量处理也是同一规则：每个视频旁边生成自己的 `_subtitle` 文件夹。

---

## 阶段一：首次检查 / 初始化 / smoke-test

从主入口开始：

```text
/lzp-video-subtitle
```

首次会做三件事：

```text
1. 检查电脑环境
2. 如有缺失，确认后补齐必要模型和依赖
3. 用本地样本做 smoke-test
```

检查本身不会安装或下载东西。

如果需要初始化，agent 会先告诉你：

```text
缺什么
装在哪里
预计占用多少
是否确认开始
```

确认后才会执行安装 / 下载。

### smoke-test 必须提供本地样本

smoke-test 不内置测试视频，也不会为了测试自动下载样本。

你需要提供一个本地视频 / 音频路径：

```powershell
python scripts/video_subtitle_cli.py smoke-test --input "C:\path\sample.mp4"
```

建议样本：

```text
30-60 秒短样片最好；
如果给正式视频，CLI 会只截取前 60 秒做测试，不处理完整视频。
```

smoke-test 输出会自动放到：

```text
<runtime_home>/smoke-tests/<timestamp>/
```

不需要用户指定输出路径。

### smoke-test 通过标准

核心通过标准是：

```text
输入视频可读
ffmpeg 可抽音频
Qwen 可转写
final.srt / final.txt / review_focus.csv 生成
success = true
error = null
```

`sample_duration / rtf` 是性能统计项，不是字幕生成的通过条件。

报告里会有：

```json
{
  "success": true,
  "sample_duration": 60.01,
  "duration_available": true,
  "rtf": 1.575,
  "rtf_available": true,
  "warnings": []
}
```

如果 duration / rtf 不可用，也会明确写：

```json
{
  "success": true,
  "duration_available": false,
  "rtf_available": false,
  "warnings": ["原因说明"]
}
```

---

## 阶段二：正式生成字幕

仍然从主入口开始：

```text
/lzp-video-subtitle
```

你可以直接说：

```text
帮我给这个视频生成字幕
```

agent 会先确认词库 / profile。

如果你没有指定项目名，默认使用：

```text
general
```

然后提供正式视频或文件夹路径：

```text
单个视频：C:\Users\...\video.mp4
批量处理：C:\Users\...\videos\
```

生成完成后，请先人工检查：

```text
final.srt
final.txt
review_focus.csv
```

如果修改了字幕，请重新导出另存一份 srt 文件，后续 learn 会用它对比原始版本。

---

## 阶段三：学习 / 沉淀词库

用户可以自然语言说明：

```text
学习这份人工修正
```

需要两份文件：

```text
1. 原始生成的 final.srt
2. 人工修改后的 edited.srt / final_edited.srt
```

系统会先生成候选：

```text
learn_candidates.csv
```

这一步只生成候选，不会直接写入词库。

只有用户确认后，才会写入当前 profile；写入前会自动备份原来的 `corrections.csv`。

---

## Windows / PowerShell 注意

PowerShell 示例变量使用 `$runtimeHome`，不要使用 `$home`，因为 `$HOME` 是保留变量。

如遇终端中文乱码，可设置：

```powershell
$env:PYTHONIOENCODING = "utf-8"
```

如果 CUDA 可用，默认优先使用 GPU。

如需强制 CPU：

```powershell
python scripts/video_subtitle_cli.py run --input "C:\path\video.mp4" --cpu
```

如果复用已有 Qwen 环境：

```powershell
python scripts/video_subtitle_cli.py run --python "D:\WorkBuddy_Local\qwen_local_3060_pilot\.venv\Scripts\python.exe" --input "C:\path\video.mp4"
```

---

## 依赖分层

### 核心依赖

```text
Python
Qwen ASR 运行环境
torch / qwen_asr / modelscope / transformers
ffmpeg
```

### 推荐但不阻断

```text
ffprobe：用于 sample_duration / rtf 统计
```

没有 `ffprobe` 时，字幕生成仍可成功；报告会说明统计项是否可用。

---

## 更多说明

安装细节：

```text
references/install.md
```

CLI 规格：

```text
references/cli-spec.md
```
