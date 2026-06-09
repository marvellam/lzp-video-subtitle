# lzp-video-subtitle

本地中文字幕生成 skill。核心目标：用一个主入口完成本地 Qwen 字幕生成，并把人工修正沉淀成长期词库。

```text
主入口：/lzp-video-subtitle

内部阶段：
1. 首次检查 / 初始化：healthcheck -> setup-plan -> 用户确认 -> setup -> smoke-test
2. 正式生成字幕：选择 profile -> 提供视频 -> run / batch
3. 学习修正：对比 final.srt 与 edited.srt -> 候选确认 -> learn 写入 profile
```

默认使用 Qwen 本地模型，不把视频发到云端。

```text
视频 / 音频
→ Qwen 本地 ASR 转写
→ 时间轴 / 对齐
→ 分句 / 清理
→ final.srt / final.txt / review_focus.csv
→ 人工修正
→ learn 写回 profile 词库
```

---

## 当前边界

当前版本专注一件事：**本地生成中文字幕，并把人工确认过的修正沉淀成词库。**

当前不做：

```text
- 不自动切换 Whisper / 云端 ASR
- 不默认内置 LLM 自动改字幕
- 不在安装 skill 本体时自动下载模型
- 不把 debug 文件直接堆到用户输出根目录
```

---

## 安装与运行环境

安装 skill 本体后，不会立即下载模型。

第一次使用直接从主入口开始：

```text
/lzp-video-subtitle
```

skill 会自动执行只读检查：

```text
healthcheck -> setup-plan
```

如果环境缺少依赖或模型，会先告知缺什么、安装位置和预计占用，并等用户确认后再执行：

```text
setup -> smoke-test
```

运行环境默认放在：

```text
Windows: %LOCALAPPDATA%\lzp-video-subtitle
macOS/Linux: ~/.local/share/lzp-video-subtitle
```

Qwen Python 环境默认放在：

```text
<runtime_home>/envs/qwen-local
```

模型目录默认跟随当前 runtime home：

```text
<runtime_home>/models/qwen
```

如需复用已有 Qwen Python 环境，优先显式指定，不要重复安装：

```powershell
python scripts/video_subtitle_cli.py smoke-test --python "D:\WorkBuddy_Local\qwen_local_3060_pilot\.venv\Scripts\python.exe" --input "C:\path\sample.mp4"
```

如需复用已有模型，可显式设置：

```powershell
$env:VIDEO_SUBTITLE_MODELS_DIR = "D:\WorkBuddy_Local\qwen_local_3060_pilot\models"
```

更多安装细节见：

```text
references/install.md
```

---

## 你会得到什么

每个视频默认生成三件套：

```text
final.srt          字幕文件
final.txt          纯文本稿
review_focus.csv   建议人工重点检查的位置
```

如果你不指定输出路径，结果会默认保存在视频旁边：

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

## 第一阶段：首次检查 / 初始化 / 运行测试

入口：

```text
/lzp-video-subtitle
```

这个阶段会做三件事：

```text
1. 检查电脑环境
2. 如有缺失，补齐必要模型和依赖
3. 用 30-60 秒视频做运行测试
```

检查本身不会安装或下载东西。

如果已经具备运行环境，会直接提示“无需重复安装或下载”。

如果缺少模型或依赖，会先告诉用户需要补什么、大概占用多少空间，并等用户确认后再安装。

安装完成后，提供一个视频 / 音频文件路径做运行测试：

```text
最好是 30-60 秒短样片；
如果给正式视频，只截取前 60 秒做测试，不处理完整视频。
```

运行测试通过后，再进入正式生成字幕。

---

## 第二阶段：运行 / 生成字幕

主入口仍然是：

```text
/lzp-video-subtitle
```

用户可以自然语言说明：

```text
帮我给这个视频生成字幕
```

这个阶段会先选择一个“词库 / profile”。

如果没有项目名，默认使用：

```text
general
```

然后提供正式要处理的视频或文件夹路径。

单个视频：

```text
C:\Users\...\video.mp4
```

批量处理：

```text
C:\Users\...\videos\
```

正式生成字幕时，会同时确认输出位置：

```text
默认：保存在视频旁边的 <video_basename>_subtitle 文件夹
也可以：指定一个输出目录
```

smoke-test 是初始化阶段的测试输出，会自动放到测试目录，不需要用户指定输出路径。**但必须提供 `--input <本地视频路径>` 作为测试样本**；skill 不内置测试视频，也不会为了测试自动下载样本。

`sample_duration` / `rtf` 是性能统计项，不是字幕生成的通过条件。`ffprobe` 可让统计更完整；缺少 `ffprobe` 时 CLI 会尝试用 `ffmpeg -i` fallback，fallback 失败时仍可生成字幕，但报告会把 `duration_available=false`、`rtf_available=false` 和原因写入 `warnings`。

生成完成后，请先人工检查：

```text
final.srt
final.txt
review_focus.csv
```

如果修改了字幕，请重新导出另存一份 srt 文件。

---

## 第三阶段：学习 / 沉淀词库

主入口仍然是：

```text
/lzp-video-subtitle
```

用户可以自然语言说明：

```text
学习这份人工修正
```

需要两份字幕文件路径：

```text
1. 原始生成的 final.srt
2. 人工修改后的 final_edited.srt / edited.srt
```

如果上一步刚生成过字幕，通常能自动找到原始 `final.srt`，用户只需要提供人工修改后的版本。

系统会先对比两份字幕，生成：

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

如果 CUDA 可用，运行默认优先使用 GPU；如需强制 CPU，可在 CLI 层使用：

```powershell
python scripts/video_subtitle_cli.py run --input <video> --cpu
```

---

## 底层 CLI

底层 CLI 文件：

```text
scripts/video_subtitle_cli.py
```

内部命令包括：

```text
healthcheck / setup-plan / setup / smoke-test / init-profile / run / batch / learn
```

这些是 agent 内部能力；普通用户不需要逐个记忆。
