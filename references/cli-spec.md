# lzp-video-subtitle CLI 规格

底层 CLI 文件：

```text
scripts/video_subtitle_cli.py
```

用户主要通过三个入口使用 skill；CLI 命令是内部能力。

---

## 一、阶段入口与内部命令

| 用户入口 | 内部命令 | 说明 |
|-|-|-|
| `/lzp-video-subtitle-install` | healthcheck / setup-plan / setup / smoke-test | 安装、环境准备、运行测试 |
| `/lzp-video-subtitle-run` | init-profile / run / batch | 选择词库、索要视频、生成字幕 |
| `/lzp-video-subtitle-learn` | learn | 候选修正确认后写入词库 |

---

## 二、运行目录与状态文件

`VIDEO_SUBTITLE_HOME` 默认由 CLI 自动决定，不能放在 skill 代码目录里。

建议优先级：

```text
1. 环境变量 VIDEO_SUBTITLE_HOME
2. 用户配置目录下的 lzp-video-subtitle runtime home
```

状态文件：

```text
VIDEO_SUBTITLE_HOME/state/current.json
VIDEO_SUBTITLE_HOME/state/runs/RUN_ID.json
```

`current.json` 记录最近状态，供下一阶段接续。

---

## 三、healthcheck

```bash
python scripts/video_subtitle_cli.py healthcheck
```

只检查，不安装、不下载。

检查项：

```text
Python
ffmpeg
GPU / CUDA
runtime home
best 模型是否存在
small 模型是否存在
aligner 模型是否存在
必要 Python 依赖是否存在
```

输出应支持中文摘要和 `--json`。

---

## 四、setup-plan

```bash
python scripts/video_subtitle_cli.py setup-plan --model-tier best
python scripts/video_subtitle_cli.py setup-plan --model-tier small
```

只生成安装方案，不安装、不下载。

输出字段建议：

```json
{
  "model_tier": "best",
  "missing": [
    {"type": "python_env", "label": "Qwen Python 运行环境"},
    {"type": "model", "model_id": "Qwen/Qwen3-ASR-1.7B"}
  ],
  "setup_actions": ["install only missing items listed in missing[]"],
  "runtime_home": "...",
  "models_dir": "..."
}
```

如果 `missing=[]`，表示当前环境已满足要求，setup 不应重复安装或下载。

---

## 五、setup

```bash
python scripts/video_subtitle_cli.py setup --backend qwen-local --model-tier best
python scripts/video_subtitle_cli.py setup --backend qwen-local --model-tier small
```

执行安装 / 下载。调用前必须已经向用户确认。

执行原则：

```text
healthcheck 负责检测
setup-plan 基于检测输出 missing[]
setup 只处理 missing[]
missing=[] 时直接提示“无需重复安装或下载”
```

第一版决策：

```text
缺依赖时再安装 PyTorch / qwen_asr / modelscope 等必要依赖
缺模型时再下载对应模型
ModelScope 优先，HuggingFace fallback
```

setup 完成后更新：

```text
VIDEO_SUBTITLE_HOME/state/current.json
```

---

## 六、smoke-test

```bash
python scripts/video_subtitle_cli.py smoke-test --backend qwen-local --model-tier best --input smoke_sample.mp4
python scripts/video_subtitle_cli.py smoke-test --backend qwen-local --model-tier small --input smoke_sample.mp4
```

运行测试归属于 install 阶段。

如果用户提供完整视频，agent 可先截取：

```bash
ffmpeg -y -i full_video.mp4 -t 60 -c copy smoke_sample.mp4
```

运行测试输出建议：

```json
{
  "success": true,
  "sample_path": "smoke_sample.mp4",
  "sample_duration": 60,
  "processing_time": 72,
  "rtf": 1.2,
  "execution_path": "cpu/cuda/etc",
  "memory_oom": false,
  "recommendation": "keep_best"
}
```

结果分支：

```text
keep_best
install_or_enable_small
fix_environment
use_stronger_machine
```

---

## 七、init-profile

```bash
python scripts/video_subtitle_cli.py init-profile --profile PROFILE_NAME
python scripts/video_subtitle_cli.py init-profile --profile general
```

创建：

```text
VIDEO_SUBTITLE_HOME/profiles/PROFILE_NAME/
  lexicon.csv
  protected_terms.csv
  corrections.csv
  style_rules.yml
  feedback_log.jsonl
```

不得覆盖已有文件。

---

## 八、run

```bash
python scripts/video_subtitle_cli.py run --profile PROFILE_NAME --input video.mp4
```

如果用户未指定输出路径，默认输出到视频旁边：

```text
<input_video_dir>/<video_basename>_subtitle/
```

也允许用户指定：

```bash
python scripts/video_subtitle_cli.py run --profile PROFILE_NAME --input video.mp4 --output-dir custom_output_dir
```

标准输出：

```text
final.srt
final.txt
review_focus.csv
```

---

## 九、batch

```bash
python scripts/video_subtitle_cli.py batch --profile PROFILE_NAME --input-dir videos/
```

批量默认与单个视频同规则：每个视频旁边生成自己的输出目录。

```text
videos/lesson01.mp4 → videos/lesson01_subtitle/
videos/lesson02.mp4 → videos/lesson02_subtitle/
```

第一版只预留断点续跑状态字段，不做完整断点续跑 UI。

---

## 十、learn

```bash
python scripts/video_subtitle_cli.py learn --profile PROFILE_NAME --raw output/final.srt --edited path/to/edited.srt
```

learn 不得静默写入。

流程：

```text
1. 对比 raw 和 edited
2. 生成候选修正
3. 展示候选
4. 用户确认
5. 写入 profile
```

写入前先做轻量备份。

备份建议：

```text
VIDEO_SUBTITLE_HOME/profiles/PROFILE_NAME/backups/YYYYMMDD-HHMMSS/
```

---

## 十一、review_focus.csv 字段

当前实现字段：

```csv
idx,start,end,duration,text,risk,reason
```

字段说明：

```text
idx：字幕序号
start/end：时间码
duration：字幕持续时间
text：字幕文本
risk：review / high 等风险级别
reason：为什么建议检查，例如 short_duration / too_long / corrections:...
```

后续如要改字段，必须同步 runner、README、SKILL 和测试样例。

---

## 十二、当前实现状态

| 能力 | 状态 | 说明 |
|-|-|-|
| healthcheck | 可运行 | 只检查，不安装、不下载 |
| setup-plan | 可运行 | 基于 healthcheck 输出 `missing[]` |
| setup | 可运行 | `missing=[]` 会跳过；缺 Python env 时创建 `<runtime_home>/envs/qwen-local` 并安装依赖；缺模型时下载 |
| smoke-test | 可运行 | 用户提供短样片或完整视频；完整视频自动截取前 60 秒 |
| init-profile | 可运行 | 创建 profile，不覆盖已有文件 |
| run | 可运行 | 已接入 Qwen 本地 runner |
| batch | 可运行 | 按每个视频旁边 `_subtitle` 输出 |
| learn | 可运行 | 生成候选；确认后备份并写入 `corrections.csv` |

---

## 十三、LLM Review

第一版不进入默认 run。

后续可作为独立入口：

```text
/lzp-video-subtitle-review
```

内部命令：

```bash
video-subtitle review --profile PROFILE_NAME --input output/final.srt
```

只输出建议，不直接改 `final.srt`。
