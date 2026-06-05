# Architecture

## Product scope

`video-subtitle` is a Qwen local subtitle workflow for repeatable course/IP content production.

It is not an automatic backend router. It does not switch to Whisper based on hardware. Project-specific terms, teacher names, correction history, and style preferences live in profiles.

## Product identity

Reference tools such as `limin112/video-subtitle` appear to focus on a fixed Whisper-heavy transcription route. This skill should be differentiated by:

1. Qwen local ASR / forced-alignment route.
2. Chinese/course subtitle cleanup and review workflow.
3. Teacher/project profiles that improve through manual correction feedback.
4. Clean user-facing output with optional debug artifacts.
5. Runtime separation: code stays small; models/envs/profiles/cache live outside the skill.
6. Safe bounded discovery: no full-disk scans, no hardcoded NAS/internal paths.

## Separation of concerns

```text
skill directory: code, scripts, references
runtime home: venvs, models, tools, cache, work, logs, profiles
user output: final subtitle artifacts for one video/batch
```

Do not put `.venv`, PyTorch, model weights, profiles, or temp audio inside the skill code directory by default. Prefer an OS-local runtime home, but allow users to explicitly choose any writable path, including network/NAS paths, after healthcheck/smoke-test warnings.

## Runtime home

Default:

- Windows: `%LOCALAPPDATA%/video-subtitle`
- macOS/Linux: `~/.local/share/video-subtitle`

Override:

```bash
VIDEO_SUBTITLE_HOME=/path/to/video-subtitle
python scripts/video_subtitle_cli.py setup-plan --home /path/to/video-subtitle
```

Internal layout:

```text
home/
  envs/
    qwen-local/
  models/
    qwen/
      Qwen3-ASR-1.7B/
      Qwen3-ASR-0.6B/
      Qwen3-ForcedAligner-0.6B/
  profiles/
    <profile>/
      lexicon.csv
      protected_terms.csv
      corrections.csv
      style_rules.yml
      feedback_log.jsonl
  tools/
    ffmpeg/
  cache/
  work/
  logs/
```

## Path policy

The skill must not assume any internal user environment such as NAS drive letters, `D:\WorkBuddy_Local`, or project-specific media paths. Those are test/development examples only.

Default to local runtime paths, but allow explicit user-selected paths:

- local disk paths
- external disks
- NAS/network shares

If runtime home is a network path, warn about possible performance, permissions, path encoding, and dependency-loading issues, then verify with healthcheck/smoke tests instead of forbidding it.

## Healthcheck discovery boundaries

Default `healthcheck` does not scan the workspace, disks, or network shares. Existing Python environment discovery only happens when the user explicitly passes `--scan-root`.

`--scan-root` must stay bounded because project workspaces can contain huge generated directories, `node_modules`, media caches, network mount points, permission-sensitive paths, or symlink/junction surprises. The implementation uses a pruned `os.walk(..., followlinks=False)` scan with depth, directory-count, timeout, symlink skipping, and common heavy-directory exclusions. Do not replace it with unbounded `Path.glob("**/...")` or full-disk scanning.

If deeper discovery is needed, add explicit CLI limits first, such as `--scan-max-depth` or `--scan-timeout`, rather than silently broadening the default behavior.

## Backend policy

This skill is a Qwen local subtitle workflow.

Product decision:

- Required backend: `qwen-local`.
- Do not switch to Whisper automatically based on GPU/OS.
- Do not present `whisper-cpp` as setup-plan fallback unless the product direction explicitly changes.
- Hardware detection is used for warnings and setup feasibility, not model selection.

## Model tier policy

Current Qwen3-ASR family:

```text
best  = Qwen3-ASR-1.7B       # strongest public ASR tier, default quality-first route
small = Qwen3-ASR-0.6B       # lightweight fallback / accuracy-efficiency route
aligner = Qwen3-ForcedAligner-0.6B
```

Default to `best`. Do not select `small` only because a GPU is missing. Instead:

```text
setup-plan --model-tier best
-> setup best
-> smoke-test best on a 30-60 second sample
-> if too slow/fails/OOM, suggest downgrade to small
```

Smoke test should report:

- success/failure
- sample duration
- processing time
- RTF (real-time factor)
- detected execution path when possible, e.g. CUDA vs CPU fallback
- memory/OOM errors if any
- recommendation: keep best / downgrade to small / fix environment / use stronger machine

## Setup order

Correct order:

```text
1. healthcheck
2. setup-plan --model-tier best
3. init-profile --profile <teacher-or-project>
4. setup --backend qwen-local --model-tier best
5. smoke-test --backend qwen-local --model-tier best --profile <profile> --input <short-sample>
6. run/batch --profile <profile>
7. human review/edit
8. learn --profile <profile> --raw <generated> --edited <human-corrected>
```

`healthcheck` and `setup-plan` must not install packages or download models.

## Profile policy

Create one profile per teacher, long-running course, or major project. Profiles are long-term skill/runtime assets, not single-video outputs.

Profile path:

```text
<VIDEO_SUBTITLE_HOME>/profiles/<profile>/
  lexicon.csv
  protected_terms.csv
  corrections.csv
  style_rules.yml
  feedback_log.jsonl
```

The profile should be explained to the user during `init-profile` and referenced after each `run`:

> Review the generated subtitles. If you manually correct them, run `learn` so the correction can improve this profile for future videos from the same teacher/project.

## Output contract

Default user-facing output per video:

```text
final.srt
final.txt
review_focus.csv
```

Definitions:

- `final.srt`: subtitle file for editing software or upload.
- `final.txt`: pure readable text only; no timecodes, no SRT indexes, no subtitle formatting.
- `review_focus.csv`: human review checklist for suspicious terms, low-confidence segments, long lines, timing issues, or profile-sensitive terms.

Optional debug artifacts only when requested or needed:

```text
debug/
  run_report.json
  asr_text_raw.txt
  asr_text_clean.txt
  align_items.json
```

Do not expose debug artifacts as the default product output.

## Learning / feedback flow

Learning is profile-level correction feedback.

Expected flow:

```text
run generates final.srt/final.txt/review_focus.csv
-> user manually reviews and saves final_edited.srt or final_edited.txt
-> learn compares raw vs edited
-> learn creates reviewable learning candidates
-> user/agent confirms useful corrections
-> confirmed terms/corrections are written to <home>/profiles/<profile>/
```

Candidate files such as `learning_candidates.csv` may be written next to the edited subtitle for review, but they are not the final vocabulary store. The final learned assets belong in the profile directory.

Do not silently mutate profile dictionaries without user/agent review. Proposed changes should be reviewable before being committed.

## User-facing completion message after run

After successful `run`, the skill/agent should tell the user:

```text
Generated:
- final.srt
- final.txt
- review_focus.csv

Next recommended step:
1. Review final.srt/final.txt, especially rows in review_focus.csv.
2. Save your corrected file as final_edited.srt or final_edited.txt.
3. Run learn with the same profile:
   video-subtitle learn --profile <profile> --raw <output/final.srt> --edited <output/final_edited.srt>

Confirmed corrections will be saved to:
<VIDEO_SUBTITLE_HOME>/profiles/<profile>/
```

## Commands scaffold

Current CLI scaffolds:

```bash
python scripts/video_subtitle_cli.py healthcheck
python scripts/video_subtitle_cli.py setup-plan --model-tier best
python scripts/video_subtitle_cli.py init-profile --profile <profile>
python scripts/video_subtitle_cli.py setup --backend qwen-local --model-tier best
python scripts/video_subtitle_cli.py smoke-test --backend qwen-local --model-tier best --profile <profile> --input <short-sample>
python scripts/video_subtitle_cli.py run --profile <profile> --input <video> --output-dir <dir>
python scripts/video_subtitle_cli.py batch --profile <profile> --input-dir <dir> --output-dir <dir>
python scripts/video_subtitle_cli.py learn --profile <profile> --raw <output/final.srt> --edited <output/final_edited.srt>
```

Implementation of setup/smoke-test/run/batch/learn should wrap the validated Qwen local runner and profile learning flow after product decisions are confirmed.
