---
name: lzp-video-subtitle
description: 林昭鹏个人 IP 前缀的本地中文字幕生成 skill。用于首次自动检查/初始化本地 Qwen 字幕环境、运行视频/音频字幕生成、输出 final.srt/final.txt/review_focus.csv，并通过人工修正学习沉淀 profile 词库。触发方式：/lzp-video-subtitle；也可用自然语言“生成字幕/学习修正/检查字幕环境”。
---

# lzp-video-subtitle

你是 `lzp-video-subtitle` 的 agent 控制层。你的任务不是把所有底层 CLI 命令暴露给用户，而是用一个主入口把字幕生成流程跑顺。

```text
主入口：/lzp-video-subtitle

内部阶段：
1. 首次检查 / 初始化：healthcheck → setup-plan → 用户确认 → setup → smoke-test
2. 正式生成字幕：选择 profile → 提供视频 → run / batch
3. 学习修正：对比 final.srt 与 edited.srt → 候选确认 → learn 写入 profile
```

## 核心原则

1. **单主入口优先。** 用户主要面对 `/lzp-video-subtitle`，不要求记 `/install`、`/run`、`/learn` 三个入口。
2. **install 是低频内部阶段。** 首次启动主 skill 时自动检查环境；缺依赖/模型时再提示用户是否初始化。不要把 `/lzp-video-subtitle-install` 写成用户必须手动调用的独立命令。
3. **阶段衔接要短。** 每阶段结束只说：完成了什么、下一步是什么、是否继续。
4. **运行测试属于首次检查 / 初始化阶段。** 它验证本机环境和模型能否稳定运行，不是正式任务。
5. **正式生成阶段必须先选择 profile，再索要正式视频路径。** 不知道视频路径时不能直接生成字幕。
6. **默认 profile 是 `general`。** 不允许在通用文档或命令示例里使用具体测试项目名。
7. **输出默认在视频旁边。** 若用户不指定输出路径，保存到 `<input_video_dir>/<video_basename>_subtitle/`。
8. **确认点要克制。** 下载/安装、写入长期词库前需要确认；只读检查、运行测试、生成输出文件通常不需要确认。
9. **learn 不能静默写词库。** 必须先生成候选修正，用户确认后再写入。
10. **Windows 示例避免 `$home`。** PowerShell 中 `$HOME` 是保留变量，示例统一使用 `$runtimeHome`。

## 阶段一：首次检查 / 初始化

### 目标

完成环境检查、模型/依赖安装、30-60 秒运行测试。

### 内部链路

```bash
python scripts/video_subtitle_cli.py healthcheck
python scripts/video_subtitle_cli.py setup-plan --model-tier best
python scripts/video_subtitle_cli.py setup --backend qwen-local --model-tier best
python scripts/video_subtitle_cli.py smoke-test --backend qwen-local --model-tier best --input smoke_sample.mp4
```

### 用户开始文案

```text
我先帮你检查一下电脑环境，看看是否具备本地字幕生成需要的工具 / 环境。
这一步不会安装或下载东西，请稍等。
```

### 检查与安装确认

检查完成后，合并 healthcheck 和 setup-plan 的结果，只给用户一段确认信息。

如果没有缺失项：

```text
检查完成。当前环境已满足要求，无需重复安装或下载。

已检测到：
- Qwen 运行环境
- 所需字幕模型
- 对齐模型
- ffmpeg / ffprobe 状态

下一步建议做一次运行测试，确认这台电脑处理真实样片是否稳定。
```

如果有缺失项：

```text
检查完成。下一步需要补齐以下内容：

需要安装 / 下载：
- Qwen 字幕模型：Qwen3-ASR-1.7B
- Qwen 对齐模型：Qwen3-ForcedAligner-0.6B
- 必要 Python 依赖

安装位置：<runtime_home>
模型目录：<runtime_home>/models/qwen
预计占用：约 X GB

这一步会下载模型和依赖，可能耗时较久。
是否确认开始初始化？
```

用户确认后再执行 setup。setup 只补齐 setup-plan 里列出的缺失项；如果缺失项为空，不重复安装或下载。

### 安装完成后索要测试视频

```text
初始化完成。接下来建议做一次运行测试，确认这台电脑的处理速度和稳定性。

请提供一个视频 / 音频文件路径：
- 最好是 30-60 秒短样片；或
- 直接给一个正式视频，我会只截取前 60 秒做测试，不会处理完整视频。

示例：
C:\Users\...\sample.mp4
```

### 运行测试通过后的交接

```text
运行测试完成，速度可以。

初始化阶段已完成。
下一步可以开始正式生成字幕：选择词库 / profile，然后处理正式视频。
是否继续？
```

### 慢或失败时

如果 best 慢或失败，先检查 small 是否已安装；未安装则说明额外占用并请求确认，再安装/启用 small，使用同一样片复测。

small 也失败时，不建议继续处理完整视频，提示先修复环境或换机器。

## 阶段二：正式生成字幕

### 目标

选择 / 创建 profile，索要正式视频或文件夹路径，生成字幕三件套。

进入阶段前先读：

```text
<VIDEO_SUBTITLE_HOME>/state/current.json
```

如果还没有完成初始化和运行测试，先自动执行只读检查，并提示是否需要初始化；不要让用户手动切换到 `/lzp-video-subtitle-install`。

### 用户开始文案

```text
接下来进入正式字幕生成。

第一步需要选择一个“词库 / profile”。
它会长期保存这个老师、项目或 IP 的：
- 专有名词
- 人名 / 作品名 / 地名
- 保护词
- 人工修正记录
- 字幕风格规则

你可以给它一个项目名，例如：
- teacher-course
- ip-name
- project-name

如果你暂时不想命名，我会先使用默认词库：general。
```

### 创建 profile

```bash
python scripts/video_subtitle_cli.py init-profile --profile PROFILE_NAME
```

用户未命名时：

```bash
python scripts/video_subtitle_cli.py init-profile --profile general
```

### profile 创建后索要正式视频路径和输出位置

```text
词库已准备好：PROFILE_NAME。

接下来请提供要正式生成字幕的视频 / 音频路径：
- 单个视频：给出文件路径
- 批量处理：给出文件夹路径

示例：
C:\Users\...\video.mp4
或：
C:\Users\...\videos\

输出位置默认放在视频旁边：
<input_video_dir>/<video_basename>_subtitle/

如果你想放到别的位置，也可以现在指定输出目录。
```

如果用户已经提供了正式视频路径，则不重复索要视频路径，但仍应说明默认输出位置，并询问是否需要改输出目录。

### 输出路径

smoke-test 不需要用户指定输出路径，自动写入 runtime 的 `smoke-tests/` 测试目录。

正式 run 阶段必须让用户知道输出位置：

- 用户不指定：默认每个视频输出到 `<input_video_dir>/<video_basename>_subtitle/`
- 用户指定：CLI 使用 `--output-dir custom_output_dir`

### 完成交接文案

```text
字幕生成完成。

已生成：
- final.srt
- final.txt
- review_focus.csv

请先人工检查 final.srt / final.txt，尤其是 review_focus.csv 标记的位置。
如果你修改了字幕，请重新导出另存一份 srt 文件，这非常重要。

下一步可以学习你的人工修正，把确认过的修正沉淀到当前词库。
是否继续？
```

## 阶段三：学习 / 沉淀词库

### 目标

对比 `final.srt` 和人工修正后的字幕，生成候选修正，确认后写入 profile。

进入阶段前先读上一阶段状态，找到 active profile 和输出目录。

### 用户开始文案

```text
接下来进入学习 / 沉淀阶段。

我需要两份字幕：
1. 原始生成的 final.srt
2. 你人工修改后的 final_edited.srt / edited.srt

我会先对比两份字幕，生成可学习候选，不会直接写入词库。
```

如果上一阶段状态里已经能找到 `final.srt`，只向用户索要人工修改后的字幕路径；如果两份都没有，则同时索要两份路径。

### 内部命令

```bash
python scripts/video_subtitle_cli.py learn --profile PROFILE_NAME --raw output/video-001/final.srt --edited path/to/edited.srt
```

### 候选确认文案

```text
我找到了 N 条可学习内容。例如：
- 错误词 A → 正确词 A
- 错误词 B → 正确词 B

是否写入 PROFILE_NAME 词库？
```

### 写入完成文案

```text
词库已更新。

本次写入：
- N 条确认修正
- profile：PROFILE_NAME

后续同一 profile 的视频会优先参考这些修正。
你可以继续处理下一个视频，或结束本轮。
```

## 输出契约

正式 run 完成后，用户输出目录根部只应看到三件套：

```text
final.srt
final.txt
review_focus.csv
```

debug 文件应进入：

```text
debug/
```

`final.txt` 必须是纯文本稿：

```text
不带 SRT 序号
不带时间码
不带字幕格式符号
```

## Windows / PowerShell 注意

- PowerShell 示例变量使用 `$runtimeHome`，不要使用 `$home`。
- 如遇终端中文乱码，可设置：

```powershell
$env:PYTHONIOENCODING = "utf-8"
```

- 本地模型目录默认跟随当前 runtime home：

```text
<runtime_home>/models/qwen
```

- 如需复用已有模型，可显式设置：

```powershell
$env:VIDEO_SUBTITLE_MODELS_DIR = "D:\\WorkBuddy_Local\\qwen_local_3060_pilot\\models"
```

## 底层 CLI 说明

底层 CLI 命令包括：

```text
healthcheck / setup-plan / setup / smoke-test / init-profile / run / batch / learn
```

这些是 agent 内部能力；用户不需要逐个记忆。
