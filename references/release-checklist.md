# lzp-video-subtitle 发布前验收清单

## 入口与用户文案

- [x] 三段式入口一致：`/lzp-video-subtitle-install` / `/lzp-video-subtitle-run` / `/lzp-video-subtitle-learn`
- [x] 用户可见文案中文优先、短句、只讲当前阶段
- [x] install 阶段明确：检查不安装；缺失项需确认后补齐；无缺失项不重复安装
- [x] smoke-test 明确：用户提供样片；完整视频只截取前 60 秒；输出进测试目录
- [x] run 阶段明确：先选 profile，再提供正式视频/文件夹，再说明输出位置
- [x] run 输出位置明确：默认视频旁边 `<video_basename>_subtitle/`，也可指定输出目录
- [x] learn 阶段明确：需要 raw `final.srt` 与人工修改后的 `final_edited.srt` / `edited.srt`
- [x] learn 写入词库前必须展示候选并确认

## 输出契约

- [x] 普通用户默认看到三件套：`final.srt` / `final.txt` / `review_focus.csv`
- [x] debug 文件进入 `debug/`
- [x] `review_focus.csv` 当前字段统一：`idx,start,end,duration,text,risk,reason`

## CLI / 状态

- [x] `healthcheck` 只检查，不安装、不下载
- [x] `setup-plan` 基于 healthcheck 输出 `missing[]`
- [x] `setup` 只处理 `missing[]`；`missing=[]` 时跳过
- [x] `run --help` 不再暴露误导性 `--debug-artifacts`
- [x] 内部旧 scaffold 命名已清理为 command 命名

## 已验证流程

- [x] OpenClaw 能识别 `lzp-video-subtitle`，状态 ready
- [x] 真实样片 smoke-test 跑通
- [x] learn 候选生成：`陈贤 -> 陈衔`
- [x] learn 写入 profile 后重跑生效
- [x] 正式 run 不指定 `--output-dir` 时输出到视频旁边 `_subtitle`
- [x] 网络盘 `Z:` / UNC 路径可读写
- [x] 输出目录清理验证通过：根目录三件套 + `debug/`

## 剩余发布前缺口

- [x] setup 自动创建 venv / pip 安装依赖：缺 Python env 时创建 `<runtime_home>/envs/qwen-local`，不修改系统 Python
- [x] best 模型 `Qwen3-ASR-1.7B` 安装计划已验证：setup-plan 会识别缺失 `Qwen/Qwen3-ASR-1.7B`；本机按用户要求不下载/不运行 best
- [x] 旧 `skills/video-subtitle` 已移出 active skills，备份到 `skills_backup/video-subtitle-legacy-20260605-174739`
- [x] 发布材料已补：`LICENSE`、GitHub 风格 README、`references/install-and-publish.md`、`references/release-checklist.md`
