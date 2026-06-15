# 安装与初始化说明

这份说明只解释安装 / 初始化边界。普通用户优先阅读根目录 `README.md`。

---

## 1. 安装 skill 本体不会自动下载模型

安装 `lzp-video-subtitle` skill 本体时，只会获得：

```text
SKILL.md
README.md
references/
scripts/
```

不会自动下载 Qwen 模型，也不会自动安装 Python 依赖。

首次使用主入口时，agent 会先执行只读检查：

```text
/lzp-video-subtitle
```

内部流程：

```text
healthcheck → setup-plan → 用户确认 → setup → smoke-test
```

> 不要求用户单独记忆 `/lzp-video-subtitle-install`。install 是主入口首次启动时的内部阶段。

---

## 2. Runtime home

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

也可在 CLI 命令中显式传入：

```powershell
python scripts/video_subtitle_cli.py healthcheck --home "C:\path\runtime"
```

---

## 3. Python 环境

默认 Qwen Python 环境：

```text
<runtime_home>/envs/qwen-local
```

如果缺少 Qwen Python env，`setup` 会在 runtime home 下创建独立 venv，并安装必要依赖，不修改系统 Python。

主要依赖包括：

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

### NVIDIA / CUDA 版 PyTorch

如果检测到 NVIDIA 显卡，`setup-plan` 会检查 Qwen Python 环境里的：

```text
torch.cuda.is_available()
```

判断规则：

- 没有 Qwen Python 环境：列为缺失项，`setup` 创建环境并安装 CUDA 版 PyTorch。
- 有 Qwen Python 环境但 CUDA 不可用：列为 `CUDA 版 PyTorch` 缺失项，`setup` 会修复该环境的 PyTorch。
- 安装 / 修复后 CUDA 仍不可用：初始化失败，不会被视为成功。

默认 CUDA PyTorch 源：

```text
https://download.pytorch.org/whl/cu121
```

如需指定其他 PyTorch CUDA wheel 源，可设置：

```powershell
$env:LZP_TORCH_INDEX_URL = "https://download.pytorch.org/whl/cu124"
```

或：

```powershell
$env:VIDEO_SUBTITLE_TORCH_INDEX_URL = "https://download.pytorch.org/whl/cu124"
```

### 复用已有 Qwen Python 环境

如果机器上已经有可用 Qwen 环境，优先复用，不重复创建新环境：

```powershell
python scripts/video_subtitle_cli.py smoke-test --python "D:\WorkBuddy_Local\qwen_local_3060_pilot\.venv\Scripts\python.exe" --input "C:\path\sample.mp4"
```

---

## 4. 模型目录

模型目录默认基于当前 runtime home：

```text
<runtime_home>/models/qwen
```

如果命令传入：

```powershell
--home "C:\path\runtime"
```

默认模型目录就是：

```text
C:\path\runtime\models\qwen
```

### 复用已有模型目录

可显式设置：

```powershell
$env:VIDEO_SUBTITLE_MODELS_DIR = "D:\WorkBuddy_Local\qwen_local_3060_pilot\models"
```

也支持：

```text
LZP_VIDEO_SUBTITLE_MODELS_DIR
QWEN_SUBTITLE_MODELS
```

---

## 5. 模型策略

默认模型策略：

```text
best:  Qwen/Qwen3-ASR-1.7B
small: Qwen/Qwen3-ASR-0.6B
align: Qwen/Qwen3-ForcedAligner-0.6B
```

`setup-plan` 会列出缺失模型；`setup` 只下载缺失项。

如果 `best` 慢或失败，可以使用 `small` 复测。

---

## 6. ffmpeg / ffprobe

### 核心依赖：ffmpeg

```text
ffmpeg
```

`ffmpeg` 用于抽取音频、统一转码为 ASR 需要的 16k 单声道 WAV，并在 smoke-test 时截取 30-60 秒样片，属于当前版本的核心运行链路。

如果缺少 `ffmpeg`，`setup-plan` 会把它列为外部阻断项；`setup` 不会静默安装外部二进制，请先用下面任一方式补齐后再继续。

Windows 推荐方式：

```powershell
winget install --id Gyan.FFmpeg -e
```

其他可选方式：

```powershell
choco install ffmpeg -y
scoop install ffmpeg
conda install -c conda-forge ffmpeg -y
```

如果网络下载不稳定，也可以使用便携包，把 `ffmpeg.exe` / `ffprobe.exe` 放到以下任一位置：

```text
<skill_root>/tools/ffmpeg.exe
<skill_root>/tools/ffmpeg/bin/ffmpeg.exe
<runtime_home>/tools/ffmpeg.exe
<runtime_home>/tools/ffmpeg/bin/ffmpeg.exe
```

也可以用环境变量显式指定：

```powershell
$env:LZP_FFMPEG_PATH = "C:\path\to\ffmpeg.exe"
$env:LZP_FFPROBE_PATH = "C:\path\to\ffprobe.exe"
```

查找顺序为：

```text
环境变量 → skill/tools → runtime/tools → PATH
```

### 推荐但不阻断：ffprobe

```text
ffprobe
```

`ffprobe` 用于读取样片时长和计算 RTF。

如果缺少 `ffprobe`，CLI 会尝试用：

```text
ffmpeg -i
```

fallback 解析时长。

如果 fallback 也失败，字幕生成仍可成功，但报告中会出现：

```json
{
  "duration_available": false,
  "rtf_available": false,
  "warnings": ["原因说明"]
}
```

这不代表字幕主链路失败。

---

## 7. smoke-test 样本要求

smoke-test 必须由用户提供本地视频 / 音频样本：

```powershell
python scripts/video_subtitle_cli.py smoke-test --input "C:\path\sample.mp4"
```

skill 不内置测试视频，也不会为了测试自动下载样本。

建议：

```text
30-60 秒短样片最好；
如果给正式视频，CLI 只截取前 60 秒做测试。
```

---

## 8. GPU / CPU

如果 CUDA 可用，`run / batch / smoke-test` 默认优先使用 GPU。

`smoke-test` 完成后必须查看报告里的执行路径：

```json
"execution_path": {
  "cuda_requested": true,
  "cuda_available": true,
  "cuda_device": "...",
  "device_used": "cuda:0"
}
```

只有 `device_used` 为 `cuda:0`（或其他 cuda 设备）时，才说明这次 smoke-test 真的走了 GPU。
如果 `cuda_available=false` 或 `device_used=cpu`，即使 `success=true`，也只能说明 CPU 链路跑通，不能算 GPU 验证通过。

如需强制 CPU：

```powershell
python scripts/video_subtitle_cli.py run --input "C:\path\video.mp4" --cpu
```

---

## 9. Windows / PowerShell 注意

PowerShell 示例变量使用 `$runtimeHome`，不要使用 `$home`，因为 `$HOME` 是保留变量。

如遇终端中文乱码，可设置：

```powershell
$env:PYTHONIOENCODING = "utf-8"
```

当前 CLI 已对 subprocess 输出做 UTF-8 + errors=replace 兜底，正常情况下不需要额外处理 Windows GBK 解码问题。

首次运行如遇 `numba` cache locator 问题，当前 CLI 会默认设置：

```text
NUMBA_CACHE_DIR=<runtime_home>/numba_cache
```

通常无需用户手动处理。
