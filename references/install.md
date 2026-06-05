# 安装说明

## Skill 安装后不会自动下载模型

安装 skill 本体只会获得说明文档、agent 行为规则和本地脚本。

模型、Python 依赖、运行环境会在用户执行 `/lzp-video-subtitle-install` 后，通过以下流程处理：

```text
healthcheck -> setup-plan -> 用户确认 -> setup -> smoke-test
```

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
