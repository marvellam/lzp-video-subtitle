# lzp-video-subtitle

本地中文字幕生成 skill。核心目标：让用户用三段式流程完成字幕生成，并把人工修正沉淀成长期词库。

```text
1. /lzp-video-subtitle-install  安装 / 环境准备 / 运行测试
2. /lzp-video-subtitle-run      选择词库 / 提供视频 / 生成字幕
3. /lzp-video-subtitle-learn    学习 / 沉淀词库
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

第一次使用请从：

```text
/lzp-video-subtitle-install
```

开始。

它会按以下顺序处理：

```text
healthcheck -> setup-plan -> 用户确认 -> setup -> smoke-test
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

## 第一步：安装 / 环境准备 / 运行测试

入口：

```text
/lzp-video-subtitle-install
```

这个阶段会做三件事：

```text
1. 检查电脑环境
2. 如有缺失，补齐必要模型和依赖
3. 用 30-60 秒视频做运行测试
```

检查本身不会安装或下载东西。

如果已经具备运行环境，我会直接告诉你“无需重复安装或下载”。

如果缺少模型或依赖，我会先告诉你需要补什么、大概占用多少空间，并等你确认后再安装。

安装完成后，我会让你提供一个视频 / 音频文件路径做运行测试：

```text
最好是 30-60 秒短样片；
如果你给正式视频，我只截取前 60 秒做测试，不处理完整视频。
```

运行测试通过后，才建议进入下一阶段。

---

## 第二步：运行 / 生成字幕

入口：

```text
/lzp-video-subtitle-run
```

这个阶段会先让你选择一个“词库 / profile”。

如果你没有项目名，默认使用：

```text
general
```

然后我会让你提供正式要处理的视频或文件夹路径。

单个视频：

```text
C:\Users\...\video.mp4
```

批量处理：

```text
C:\Users\...\videos\
```

正式生成字幕时，我会同时确认输出位置：

```text
默认：保存在视频旁边的 <video_basename>_subtitle 文件夹
也可以：你指定一个输出目录
```

smoke-test 是安装阶段的测试输出，会自动放到测试目录，不需要你指定输出路径。

生成完成后，请先人工检查：

```text
final.srt
final.txt
review_focus.csv
```

如果你修改了字幕，请重新导出另存一份 srt 文件，这非常重要。

---

## 第三步：学习 / 沉淀词库

入口：

```text
/lzp-video-subtitle-learn
```

请提供两份字幕文件路径：

```text
1. 原始生成的 final.srt
2. 人工修改后的 final_edited.srt / edited.srt
```

如果上一步刚刚生成过字幕，我通常能自动找到原始 `final.srt`，你只需要提供人工修改后的版本。

我会先对比两份字幕，生成：

```text
learn_candidates.csv
```

这一步只生成候选，不会直接写入词库。

只有你确认后，才会写入当前 profile；写入前会自动备份原来的 `corrections.csv`。

---

## 用户会看到的关键提示

### 检查环境

```text
你好，我先帮你检查一下电脑环境，看看是否具备所有需要的工具 / 环境。
这一步不会安装或下载东西，请稍等。
```

### 没有缺失项

```text
检查完成。当前环境已满足要求，无需重复安装或下载。
下一步建议做一次运行测试。
```

### 有缺失项

```text
检查完成。下一步需要补齐以下内容：
- ...

这一步会下载模型和依赖，可能耗时较久。
是否确认开始安装？
```

### 索要运行测试样片

```text
请提供一个视频 / 音频文件路径：
- 最好是 30-60 秒短样片；或
- 直接给一个正式视频，我会只截取前 60 秒做测试，不会处理完整视频。
```

### 正式生成前确认输出位置

```text
输出路径可以由你指定。
如果你不指定，我会默认把字幕结果保存在视频旁边：
<input_video_dir>/<video_basename>_subtitle/
```

### 生成完成

```text
字幕生成完成。

已生成：
- final.srt
- final.txt
- review_focus.csv

请先人工检查 final.srt / final.txt，尤其是 review_focus.csv 标记的位置。
```

### 学习写入前

```text
我找到了 N 条可学习内容。
是否写入 PROFILE_NAME 词库？
```

---

## 重要决策

- skill 名称：`lzp-video-subtitle`
- 默认 profile：`general`
- 默认模型：`Qwen3-ASR-1.7B`
- 降级模型：`Qwen3-ASR-0.6B`
- 对齐模型：`Qwen3-ForcedAligner-0.6B`
- 模型下载源：ModelScope 优先，HuggingFace fallback
- LLM review：后续作为独立入口，不进入默认 run 流程

---

## 内部 CLI

底层 CLI 规格见：

```text
references/cli-spec.md
```

Agent 行为规则见：

```text
SKILL.md
```

示例输出见：

```text
references/examples/sample-output/
```
