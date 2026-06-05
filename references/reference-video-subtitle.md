# Lessons from limin112/video-subtitle

Reference repo tested/inspected: `https://github.com/limin112/video-subtitle`.

## Useful patterns

- Keep a stable intermediate format (`cues.json`).
- Install heavy dependencies once, then reuse.
- Do not require the user to write correction tables; the agent can produce per-video corrections.
- Avoid hard cutting with model options like `-ml`; natural segments/semantic boundaries are better.
- Review artifacts matter: `review.html` / `review_focus.csv` make manual correction tractable.
- Long subtitles should be split by text width/semantic boundaries, not raw character count only.

## Differences in our project

- We first need editable SRT for剪辑软件, not hard subtitle burn-in.
- Our current default MVP backend is Qwen local + ForcedAligner, not whisper.cpp.
- We need Windows/NVIDIA support first, but must design cross-platform setup planning.
- Our runtime must not live in NAS or Chinese network paths.

## Architecture consequence

The skill should provide scripts and workflow, but should not bundle model weights or `.venv`. Setup must detect machine capabilities and ask the user before downloading large dependencies.
