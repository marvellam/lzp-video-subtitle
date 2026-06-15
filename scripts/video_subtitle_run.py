# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import re
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

PUNCT = set("，。！？；：、,.!?;:()（）《》〈〉“”\"'‘’…—-· ")
SENTENCE_END = set("。！？!?；;")
SOFT_BREAK = set("，,、：:")
PUNCT_RE = re.compile(r"[，。！？；：、,.!?;:()（）《》〈〉“”\"'‘’…—\-·\s]")
DEFAULT_CORRECTIONS = {}
PROTECTED_DEFAULT = set()


def now():
    return time.perf_counter()


def fmt_ts(t: float) -> str:
    t = max(0.0, float(t))
    h = int(t // 3600); t -= h * 3600
    m = int(t // 60); t -= m * 60
    s = int(t); ms = int(round((t - s) * 1000))
    if ms == 1000:
        s += 1; ms = 0
    if s == 60:
        m += 1; s = 0
    if m == 60:
        h += 1; m = 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def run(cmd):
    print("$", " ".join(map(str, cmd)), flush=True)
    return subprocess.run(cmd, check=True, text=True, encoding="utf-8", errors="replace")


def find_ffmpeg() -> str:
    root = Path(__file__).resolve().parent.parent
    env_candidates = [
        os.environ.get("LZP_FFMPEG_PATH"),
        os.environ.get("VIDEO_SUBTITLE_FFMPEG_PATH"),
        os.environ.get("FFMPEG_PATH"),
    ]
    for env_path in env_candidates:
        if env_path and Path(env_path).exists():
            return str(Path(env_path))
    names = ["ffmpeg.exe", "ffmpeg"] if os.name == "nt" else ["ffmpeg"]
    candidates = []
    for name in names:
        candidates.extend([
            root / "tools" / name,
            root / "tools" / "ffmpeg" / name,
            root / "tools" / "ffmpeg" / "bin" / name,
        ])
        home_env = os.environ.get("VIDEO_SUBTITLE_HOME") or os.environ.get("LZP_VIDEO_SUBTITLE_HOME")
        if home_env:
            home = Path(home_env)
            candidates.extend([
                home / "tools" / name,
                home / "tools" / "ffmpeg" / name,
                home / "tools" / "ffmpeg" / "bin" / name,
            ])
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    return "ffmpeg"


def ffmpeg_extract(video: Path, wav: Path):
    wav.parent.mkdir(parents=True, exist_ok=True)
    run([find_ffmpeg(), "-y", "-i", str(video), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)])


def snapshot(model_id: str, local_dir: Path):
    if (local_dir / "model.safetensors").exists():
        print(f"Model exists: {local_dir}", flush=True)
        return str(local_dir)
    from modelscope import snapshot_download
    return snapshot_download(model_id, local_dir=str(local_dir))


def normalize_text(s: str) -> str:
    try:
        from opencc import OpenCC
        if not hasattr(normalize_text, "_cc"):
            normalize_text._cc = OpenCC("t2s")  # type: ignore[attr-defined]
        s = normalize_text._cc.convert(s)  # type: ignore[attr-defined]
    except Exception:
        pass
    return s


def strip_punct(s: str) -> str:
    return PUNCT_RE.sub("", s or "")


def char_len(s: str) -> int:
    return len(strip_punct(s))


def load_lexicon(path: Path):
    corrections = dict(DEFAULT_CORRECTIONS)
    protected = set(PROTECTED_DEFAULT)
    if path.exists():
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                wrong = (row.get("wrong") or "").strip()
                correct = (row.get("correct") or "").strip()
                conf = (row.get("confidence") or "").strip().lower()
                if correct:
                    protected.add(correct)
                if wrong and correct and wrong != correct and conf in {"", "auto", "high"}:
                    corrections[wrong] = correct
    return corrections, sorted(protected, key=len, reverse=True)


def apply_corrections(s: str, corrections: dict[str, str]):
    hits = []
    out = s
    for wrong, correct in corrections.items():
        if wrong in out:
            out = out.replace(wrong, correct)
            hits.append(f"{wrong}->{correct}")
    return out, hits


def visible_boundaries_from_punct(text: str) -> set[int]:
    """Return 1-based visible char positions after which punctuation suggests a semantic break."""
    boundaries: set[int] = set()
    count = 0
    for ch in text:
        if strip_punct(ch):
            count += 1
        elif ch in SENTENCE_END or ch in SOFT_BREAK:
            if count > 0:
                boundaries.add(count)
    return boundaries


@dataclass
class CharItem:
    text: str
    start: float
    end: float


@dataclass
class Cue:
    idx: int
    start: float
    end: float
    text: str
    source: str = ""


def tokenize_with_protection(text: str, protected_terms: list[str]) -> list[str]:
    tokens = []
    i = 0
    while i < len(text):
        matched = None
        for term in protected_terms:
            if term and text.startswith(term, i):
                matched = term
                break
        if matched:
            tokens.append(matched); i += len(matched)
        else:
            tokens.append(text[i]); i += 1
    return tokens


def items_to_chars(items, protected_terms: list[str]) -> list[CharItem]:
    chars: list[CharItem] = []
    for it in items:
        raw = normalize_text(str(it.get("text", "")))
        if not raw:
            continue
        st = float(it["start_time"]); en = float(it["end_time"])
        toks = tokenize_with_protection(raw, protected_terms)
        visible = [t for t in toks if strip_punct(t)]
        n = max(1, len(visible))
        dur = max(0.01, en - st)
        k = 0
        for tok in toks:
            if not strip_punct(tok):
                continue
            cst = st + dur * k / n
            cen = st + dur * (k + 1) / n
            k += 1
            # If protected token is multi-char, split timing evenly per char for subtitle flexibility.
            for j, ch in enumerate(tok):
                if not strip_punct(ch):
                    continue
                ccst = cst + (cen - cst) * j / max(1, len(tok))
                ccen = cst + (cen - cst) * (j + 1) / max(1, len(tok))
                chars.append(CharItem(ch, ccst, ccen))
    return chars


def chars_text(chars: list[CharItem]) -> str:
    return "".join(c.text for c in chars if strip_punct(c.text))


def choose_split(chars: list[CharItem], max_chars: int, protected_ranges: list[tuple[int, int]] | None = None, base_offset: int = 0) -> int:
    if len(chars) <= 1:
        return 1
    protected_ranges = protected_ranges or []
    bad_start = set("的了呢吗啊呀是不就和与及、，。！？；：")
    good_end = set("的了着过是有在就都也而但却和与及嘛啊呢呀")
    candidates = []
    total = len(chars)

    def inside_protected(split_abs_pos: int) -> bool:
        # split_abs_pos is visible char count before right part, 1-based boundary position.
        for st, en in protected_ranges:
            if st < split_abs_pos < en:
                return True
        return False

    for i in range(1, total):
        left = i; right = total - i
        split_abs = base_offset + i
        next_first = chars[i].text if i < total else ""
        prev = chars[i-1].text
        punct_priority = 0
        if prev in SENTENCE_END:
            punct_priority = 12
        elif prev in SOFT_BREAK:
            punct_priority = 10
        elif prev in good_end:
            punct_priority = 8
        overflow_penalty = 100 if left > max_chars else 0
        bad_start_penalty = 80 if next_first in bad_start else 0
        tiny_penalty = 25 if left < 3 or right < 3 else 0
        protected_penalty = 500 if inside_protected(split_abs) else 0
        exact_hard_cut_penalty = 12 if left == max_chars and punct_priority == 0 else 0
        score = overflow_penalty + bad_start_penalty + tiny_penalty + protected_penalty + exact_hard_cut_penalty + abs(max_chars - left) - punct_priority * 3
        candidates.append((score, i))
    candidates.sort()
    return candidates[0][1]


def protected_ranges_for_text(clean_text: str, protected_terms: list[str]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for term in protected_terms:
        term_clean = strip_punct(term)
        if not term_clean or len(term_clean) <= 1:
            continue
        start = 0
        while True:
            idx = clean_text.find(term_clean, start)
            if idx < 0:
                break
            # store visible boundary positions: term spans (idx, idx+len). split inside is st < split < en
            ranges.append((idx, idx + len(term_clean)))
            start = idx + 1
    return ranges


def split_long_span(span: list[CharItem], max_chars: int, protected_ranges: list[tuple[int, int]], base_offset: int) -> list[tuple[list[CharItem], str, int]]:
    """Recursively split a semantic span into <=max_chars pieces. Returns (chars, source, base_offset)."""
    if len(span) <= max_chars or len(span) <= 1:
        return [(span, "semantic_span", base_offset)]
    idx = choose_split(span, max_chars, protected_ranges, base_offset)
    left = span[:idx]
    right = span[idx:]
    out: list[tuple[list[CharItem], str, int]] = []
    if left:
        out.extend(split_long_span(left, max_chars, protected_ranges, base_offset))
    if right:
        out.extend(split_long_span(right, max_chars, protected_ranges, base_offset + len(left)))
    return out


def segment_chars(chars: list[CharItem], max_chars: int, min_duration: float, hard_min_duration: float, semantic_boundaries: set[int] | None = None, protected_terms: list[str] | None = None, soft_max_chars: int | None = None, hard_max_chars: int | None = None) -> list[Cue]:
    """Formal v5 segmentation:
    1) first cut by ASR punctuation-derived semantic boundaries;
    2) recursively split only overlong spans;
    3) protect known terms from being split in the middle when possible.
    """
    semantic_boundaries = semantic_boundaries or set()
    protected_terms = protected_terms or []
    full_text = chars_text(chars)
    protected_ranges = protected_ranges_for_text(full_text, protected_terms)

    spans: list[tuple[list[CharItem], int]] = []
    buf: list[CharItem] = []
    span_start_offset = 0
    visible_pos = 0
    for ch in chars:
        buf.append(ch)
        visible_pos += 1
        if visible_pos in semantic_boundaries:
            if buf:
                spans.append((buf, span_start_offset))
            buf = []
            span_start_offset = visible_pos
    if buf:
        spans.append((buf, span_start_offset))

    cues: list[Cue] = []
    for span, offset in spans:
        for part, source, part_offset in split_long_span(span, max_chars, protected_ranges, offset):
            txt = chars_text(part)
            if not txt:
                continue
            cues.append(Cue(len(cues)+1, part[0].start, max(part[-1].end, part[0].start + 0.01), txt, source if len(part) <= max_chars else "split_overlong"))

    # Merge short fragments with neighbors. 14字是目标，不是绝对硬切；为换取语义完整，允许轻微软溢出。
    soft_max = soft_max_chars or (max_chars + 2)
    hard_max = hard_max_chars or (max_chars + 4)
    merged: list[Cue] = []
    for c in cues:
        dur = c.end - c.start
        if merged and dur < min_duration and char_len(merged[-1].text + c.text) <= soft_max:
            prev = merged[-1]
            prev.text += c.text
            prev.end = c.end
            prev.source += "+merge_short"
        else:
            merged.append(c)
    # second pass: merge a short cue into the following cue when previous merge was not possible
    i = 0
    merged2: list[Cue] = []
    while i < len(merged):
        c = merged[i]
        dur = c.end - c.start
        if dur < min_duration and i + 1 < len(merged) and char_len(c.text + merged[i+1].text) <= soft_max:
            nxt = merged[i+1]
            merged2.append(Cue(0, c.start, nxt.end, c.text + nxt.text, c.source + "+merge_next_short"))
            i += 2
        else:
            merged2.append(c)
            i += 1
    # normalize: after merges, any cue above hard_max is split again; any cue above soft_max is review-worthy but tolerated.
    normalized: list[Cue] = []
    for c in merged2:
        if char_len(c.text) <= hard_max:
            normalized.append(c)
            continue
        pseudo = [CharItem(ch, c.start + (c.end - c.start) * i / max(1, len(c.text)), c.start + (c.end - c.start) * (i + 1) / max(1, len(c.text))) for i, ch in enumerate(c.text)]
        for part, source, _ in split_long_span(pseudo, soft_max, protected_ranges_for_text(c.text, protected_terms), 0):
            if part:
                normalized.append(Cue(0, part[0].start, part[-1].end, chars_text(part), c.source + "+normalize_oversize"))
    for i, c in enumerate(normalized, 1):
        c.idx = i
    return normalized


def write_srt(cues: list[Cue], path: Path):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        for c in cues:
            f.write(f"{c.idx}\n{fmt_ts(c.start)} --> {fmt_ts(c.end)}\n{c.text}\n\n")


def make_review(cues: list[Cue], path: Path, max_chars: int, min_duration: float, correction_hits: list[str]):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["idx", "start", "end", "duration", "text", "risk", "reason"])
        writer.writeheader()
        for c in cues:
            dur = c.end - c.start
            reasons = []
            if char_len(c.text) > max_chars:
                reasons.append("too_long")
            if dur < min_duration:
                reasons.append("short_duration")
            if re.search(r"[A-Za-z]", c.text):
                reasons.append("latin_leftover")
            # surface known correction context in first row only; avoids fake per-cue mapping for v5
            if c.idx == 1 and correction_hits:
                reasons.append("corrections:" + ";".join(correction_hits))
            if reasons:
                writer.writerow({
                    "idx": c.idx,
                    "start": fmt_ts(c.start),
                    "end": fmt_ts(c.end),
                    "duration": round(dur, 2),
                    "text": c.text,
                    "risk": "high" if "too_long" in reasons or "latin_leftover" in reasons else "review",
                    "reason": "|".join(reasons),
                })


def clean_root_debug_files(results: Path, debug: Path) -> None:
    """Keep user-facing output root clean: only final.srt/final.txt/review_focus.csv by default."""
    debug.mkdir(parents=True, exist_ok=True)
    debug_names = {
        "align_items.json",
        "asr_text_clean.txt",
        "asr_text_raw.txt",
        "run_report.json",
        "README.md",
        "lzp_run_config.json",
    }
    for name in debug_names:
        src = results / name
        if not src.exists() or not src.is_file():
            continue
        dst = debug / name
        if dst.exists():
            dst.unlink()
        src.replace(dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.json")
    args = ap.parse_args()
    root = Path(__file__).resolve().parent.parent
    cfg = json.loads((root / args.config).read_text(encoding="utf-8"))
    results = Path(cfg.get("output_dir", str(root / "results")))
    debug = results / "debug"
    work = Path(os.environ.get("QWEN_SUBTITLE_WORK", str(root / "work")))
    models = Path(os.environ.get("QWEN_SUBTITLE_MODELS", str(root / "models")))
    for p in (results, debug, work, models):
        p.mkdir(parents=True, exist_ok=True)
    video = Path(cfg["video_path"])
    if not video.exists():
        raise FileNotFoundError(f"视频不存在：{video}\n请检查输入路径")
    lexicon_path = Path(cfg.get("project_lexicon", "lexicon.csv"))
    if not lexicon_path.is_absolute():
        lexicon_path = root / lexicon_path
    corrections, protected = load_lexicon(lexicon_path)

    import torch
    cuda = bool(torch.cuda.is_available())
    device = "cuda:0" if (cfg.get("prefer_cuda", True) and cuda) else "cpu"
    dtype = torch.float16 if device.startswith("cuda") else torch.float32

    report = {"system": {"platform": platform.platform(), "python": sys.version, "torch": torch.__version__, "cuda_available": cuda, "cuda_device": torch.cuda.get_device_name(0) if cuda else None, "device_used": device, "dtype": str(dtype)}, "input": str(video)}

    t = now(); wav = work / "audio16k.wav"; ffmpeg_extract(video, wav); report["extract_audio_sec"] = round(now()-t, 2)
    asr_dir = models / cfg.get("asr_model", "Qwen/Qwen3-ASR-0.6B").rstrip("/").split("/")[-1]
    align_dir = models / cfg.get("aligner_model", "Qwen/Qwen3-ForcedAligner-0.6B").rstrip("/").split("/")[-1]
    t = now(); snapshot(cfg.get("asr_model", "Qwen/Qwen3-ASR-0.6B"), asr_dir); report["download_asr_sec_if_needed"] = round(now()-t, 2)
    t = now(); snapshot(cfg.get("aligner_model", "Qwen/Qwen3-ForcedAligner-0.6B"), align_dir); report["download_aligner_sec_if_needed"] = round(now()-t, 2)

    from qwen_asr import Qwen3ASRModel, Qwen3ForcedAligner
    t = now(); asr = Qwen3ASRModel.from_pretrained(str(asr_dir), dtype=dtype, device_map=device, max_inference_batch_size=1, max_new_tokens=2048); report["load_asr_sec"] = round(now()-t, 2)
    t = now(); asr_results = asr.transcribe(audio=str(wav), language=cfg.get("language", "Chinese")); report["asr_sec"] = round(now()-t, 2)
    raw_text = normalize_text(asr_results[0].text)
    corrected_text, hits = apply_corrections(raw_text, corrections)
    semantic_boundaries = visible_boundaries_from_punct(corrected_text)
    clean_for_align = strip_punct(corrected_text)
    (debug / "asr_text_raw.txt").write_text(raw_text, encoding="utf-8-sig")
    (debug / "asr_text_clean.txt").write_text(clean_for_align, encoding="utf-8-sig")
    del asr
    if cuda:
        torch.cuda.empty_cache()

    t = now(); aligner = Qwen3ForcedAligner.from_pretrained(str(align_dir), dtype=dtype, device_map=device); report["load_aligner_sec"] = round(now()-t, 2)
    t = now(); align_results = aligner.align(audio=str(wav), text=clean_for_align, language=cfg.get("language", "Chinese")); report["align_sec"] = round(now()-t, 2)
    items = [{"text": x.text, "start_time": x.start_time, "end_time": x.end_time} for x in align_results[0].items]
    (debug / "align_items.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    chars = items_to_chars(items, protected)
    cues = segment_chars(chars, int(cfg.get("max_chars", 14)), float(cfg.get("min_duration", 1.0)), float(cfg.get("hard_min_duration", 0.6)), semantic_boundaries, protected, int(cfg.get("soft_max_chars", int(cfg.get("max_chars", 14)) + 2)), int(cfg.get("hard_max_chars", int(cfg.get("max_chars", 14)) + 4)))
    write_srt(cues, results / "final.srt")
    (results / "final.txt").write_text("\n".join(c.text for c in cues), encoding="utf-8-sig")
    make_review(cues, results / "review_focus.csv", int(cfg.get("soft_max_chars", int(cfg.get("max_chars", 14)) + 2)), float(cfg.get("min_duration", 1.0)), hits)
    report["rules"] = {"target_chars": cfg.get("max_chars", 14), "soft_max_chars": cfg.get("soft_max_chars", int(cfg.get("max_chars", 14)) + 2), "hard_max_chars": cfg.get("hard_max_chars", int(cfg.get("max_chars", 14)) + 4), "max_lines": 1, "min_duration_target": cfg.get("min_duration", 1.0), "hard_min_duration": cfg.get("hard_min_duration", 0.6), "remove_punctuation": True}
    report["counts"] = {"align_items": len(items), "chars": len(chars), "final_cues": len(cues), "review_rows": max(0, sum(1 for _ in open(results / "review_focus.csv", encoding="utf-8-sig"))-1), "correction_hits": hits}
    report["note"] = "v5：Qwen 本地 ASR + ForcedAligner + 简化语义/长度分句。final.srt 才是本轮需要评估的成品候选。"
    (debug / "run_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (debug / "README.md").write_text("# Qwen local runner debug report\n\n普通用户优先检查输出目录根部的 final.srt / final.txt / review_focus.csv。\n\n" + json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    clean_root_debug_files(results, debug)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
