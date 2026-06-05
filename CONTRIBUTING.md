# Contributing

Thanks for considering improvements to `lzp-video-subtitle`.

## Product principles

This project is intentionally conservative:

- Local-first: video/audio should not be uploaded by default.
- User-facing flow should stay simple: install / run / learn.
- Do not add LLM auto-correction into the default pipeline unless explicitly designed and reviewed.
- Do not silently write to long-term profile dictionaries; always generate candidates and ask for confirmation.
- Keep the output root clean: only `final.srt`, `final.txt`, `review_focus.csv`, plus optional `debug/`.

## Development checks

Before submitting changes, run at least:

```bash
python -m py_compile scripts/video_subtitle_cli.py scripts/video_subtitle_run.py
python scripts/video_subtitle_cli.py healthcheck
python scripts/video_subtitle_cli.py setup-plan --model-tier small
```

For changes touching the runner, also run a short smoke-test sample.

## Documentation sync

If behavior changes, update all relevant files:

- `README.md`
- `SKILL.md`
- `references/cli-spec.md`
- `references/release-checklist.md`

## Review focus

Please pay special attention to:

- user-facing Chinese wording
- install confirmation points
- profile write confirmation
- no accidental cloud upload
- no debug clutter in the output root
