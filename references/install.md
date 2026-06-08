# 安装说明

## Skill 安装后不会自动下载模型

安装 skill 本体只会获得说明文档、agent 行为规则和本地脚本。

模型、Python 依赖、运行环境会在用户首次使用主入口后，由 agent 自动检查并在确认后初始化：

```text
/lzp-video-subtitle
```

内部流程：

```text
healthcheck -> setup-plan -> 用户确认 -> setup -> smoke-test
```

> 不再要求用户单独记忆 `/lzp-video-subtitle-install`。install 是主入口首次启动时的内部阶段。

## Runtime home

默认 runtime home：

```text
Windows: %LOCALAPPDATA%\lzp-video-subtitle
macOS/Linux: ~/.local/share/lzp-video-subtitle
```

可通过环境变量覆盖：

```text
LZP_VIDEO_SUBTITLE_HOME
VIDEO_SUBTITLE_HOME
```

## 模型目录

模型目录默认基于当前命令解析出的 runtime home：

```text
<runtime_home>/models/qwen
```

如果命令传入 `--home <runtime>`，默认模型目录就是：

```text
<runtime>/models/qwen
```

如需复用已有模型目录，可显式设置：

```powershell
$env:VIDEO_SUBTITLE_MODELS_DIR = "D:\path\to\qwen\models"
```

也支持：

```text
LZP_VIDEO_SUBTITLE_MODELS_DIR
QWEN_SUBTITLE_MODELS
```

## Python 环境

产品默认使用独立环境：

```text
<runtime_home>/envs/qwen-local
```

缺少 Qwen Python env 时，setup 会创建这个 venv，并安装：

```text
torch
qwen-asr
modelscope
transformers
accelerate
librosa
soundfile
qwen-omni-utils
```

不会修改系统 Python。

## 模型

默认模型策略：

```text
best:  Qwen/Qwen3-ASR-1.7B
small: Qwen/Qwen3-ASR-0.6B
align: Qwen/Qwen3-ForcedAligner-0.6B
```

setup-plan 会列出缺失模型；setup 只下载缺失项。

## Windows / PowerShell 注意

PowerShell 示例变量使用 `$runtimeHome`，不要使用 `$home`，因为 `$HOME` 是保留变量。

如遇终端中文乱码，可设置：

```powershell
$env:PYTHONIOENCODING = "utf-8"
```

首次运行如遇 `numba` cache locator 问题，当前 CLI 会默认设置：

```text
NUMBA_CACHE_DIR=<output_parent>/numba_cache
```

通常无需用户手动处理。

## GPU / CPU

如果 CUDA 可用，run / batch / smoke-test 默认优先使用 GPU。

如需强制 CPU，可加：

```powershell
python scripts/video_subtitle_cli.py run --input <video> --cpu
```

## ffmpeg / ffprobe

- `ffmpeg` 是音频抽取和 smoke-test 截样片所需依赖。
- `ffprobe` 用于读取样片时长和计算 RTF。
- 如果缺少 `ffprobe`，CLI 会尝试用 `ffmpeg -i` 输出 fallback 解析时长；healthcheck 仍会单独提示 ffprobe 状态。
