# Qwen local MVP

## Validated chain

```text
Qwen3-ASR-0.6B -> Qwen3-ForcedAligner-0.6B -> segmenter -> SRT/review
```

Validated on Windows + NVIDIA GeForce RTX 3050 Laptop GPU using a local venv on an English D: path.

## Current segmentation strategy

- Use ASR punctuation to create semantic spans.
- Recursively split overlong spans.
- Avoid splitting protected terms.
- Merge short fragments when within limits.
- Use length bands:
  - target: 14 chars
  - soft max: 16 chars
  - hard max: 18 chars

## Current MVP results

Batch directory:

```text
qwen_local_gpu_v5_production/results_batch_3samples/20260604_202834
```

Three samples succeeded:

| sample | cues | review rows |
|---|---:|---:|
| 西方画裸女 | 34 | 3 |
| 画得跟真的一样 | 44 | 1 |
| 有些画不是绘画 | 37 | 1 |

## Known limits

- ASR may hallucinate or misrecognize phrases, e.g. `放得心钱啪啪啪`.
- `review_focus.csv` currently flags length/duration/corrections; future versions should add suspicious-text heuristics.
- The MVP runner is not yet a polished package installer.
- NAS-hosted `.venv` failed because `nagisa/dynet` could not read model files under Chinese network paths.

## Engineering rule

Use local runtime paths for env/models/work. NAS can hold media and outputs, not Python environments.
