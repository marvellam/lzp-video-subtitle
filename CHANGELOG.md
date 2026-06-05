# Changelog

## 0.1.0 - 2026-06-05

### Added

- Three-stage user flow:
  - `/lzp-video-subtitle-install`
  - `/lzp-video-subtitle-run`
  - `/lzp-video-subtitle-learn`
- Local Qwen ASR runner integration.
- `healthcheck -> setup-plan -> setup` install flow.
- Runtime venv setup at `<runtime_home>/envs/qwen-local` when Python env is missing.
- Model plan/download support for:
  - `Qwen/Qwen3-ASR-1.7B`
  - `Qwen/Qwen3-ASR-0.6B`
  - `Qwen/Qwen3-ForcedAligner-0.6B`
- Smoke-test flow with 30-60 second sample handling.
- Default run output next to each input video: `<video_basename>_subtitle/`.
- Standard user-facing outputs:
  - `final.srt`
  - `final.txt`
  - `review_focus.csv`
- Debug artifacts under `debug/`.
- Profile learning workflow:
  - compare raw `final.srt` and human-edited subtitle
  - generate `learn_candidates.csv`
  - write confirmed corrections into profile with backup

### Verified

- Real sample smoke-test passed with Qwen small model.
- Formal run passed on a network-drive video path.
- Profile correction `陈贤 -> 陈衔` applied on rerun.
- OpenClaw recognizes the skill as ready.

### Not yet verified

- Real `Qwen3-ASR-1.7B` best-model run on this machine. The setup-plan correctly detects the missing best model, but it was intentionally not downloaded locally.
