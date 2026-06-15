# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SKILL_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_SCAN_MAX_DEPTH = 4
DEFAULT_SCAN_MAX_DIRS = 800
DEFAULT_SCAN_TIMEOUT_SECONDS = 8
SKIP_SCAN_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".cache",
    "cache",
    "logs",
    "tmp",
    "temp",
}


def _binary_names(name: str) -> list[str]:
    if os.name == "nt" and not name.lower().endswith(".exe"):
        return [f"{name}.exe", name]
    return [name]


def _first_existing_binary(candidates: list[Path]) -> str | None:
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    return None


def find_tool_binary(name: str, *, home: Path | None = None) -> str | None:
    """Find ffmpeg-family binaries consistently across all CLI stages.

    Lookup order is intentionally stable:
    1. explicit environment variable, e.g. LZP_FFMPEG_PATH / VIDEO_SUBTITLE_FFMPEG_PATH
    2. skill-local tools directory, e.g. <skill>/tools/ffmpeg.exe
    3. runtime-local tools directories, e.g. <home>/tools/ffmpeg.exe or <home>/tools/ffmpeg/bin/ffmpeg.exe
    4. PATH

    This keeps setup-plan, smoke-test, and run behavior aligned and allows an
    offline/portable ffmpeg zip to be dropped into a known tools directory.
    """
    upper = name.upper()
    env_candidates = [
        os.environ.get(f"LZP_{upper}_PATH"),
        os.environ.get(f"VIDEO_SUBTITLE_{upper}_PATH"),
        os.environ.get(f"{upper}_PATH"),
    ]
    for env_path in env_candidates:
        if env_path:
            p = Path(env_path)
            if p.exists() and p.is_file():
                return str(p)

    file_names = _binary_names(name)
    candidates: list[Path] = []
    for fn in file_names:
        candidates.append(SKILL_ROOT / "tools" / fn)
        candidates.append(SKILL_ROOT / "tools" / "ffmpeg" / fn)
        candidates.append(SKILL_ROOT / "tools" / "ffmpeg" / "bin" / fn)

    if home is not None:
        for fn in file_names:
            candidates.append(home / "tools" / fn)
            candidates.append(home / "tools" / "ffmpeg" / fn)
            candidates.append(home / "tools" / "ffmpeg" / "bin" / fn)

    local = _first_existing_binary(candidates)
    if local:
        return local

    return shutil.which(name) or (shutil.which(f"{name}.exe") if os.name == "nt" else None)


def default_home() -> Path:
    env = os.environ.get("VIDEO_SUBTITLE_HOME") or os.environ.get("LZP_VIDEO_SUBTITLE_HOME")
    if env:
        return Path(env)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "lzp-video-subtitle"
    return Path.home() / ".local" / "share" / "lzp-video-subtitle"


def run_probe(cmd: list[str], timeout: int = 20) -> dict:
    try:
        p = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=timeout)
        return {"ok": p.returncode == 0, "returncode": p.returncode, "stdout": (p.stdout or "").strip(), "stderr": (p.stderr or "").strip()}
    except Exception as e:
        return {"ok": False, "error": repr(e)}


def _same_path_key(path: str | Path) -> str:
    try:
        return str(Path(path).resolve()).casefold() if os.name == "nt" else str(Path(path).resolve())
    except Exception:
        return str(path).casefold() if os.name == "nt" else str(path)


def _add_unique(paths: list[str], seen: set[str], candidate: str | Path) -> None:
    c = Path(candidate)
    if not c.exists():
        return
    key = _same_path_key(c)
    if key not in seen:
        seen.add(key)
        paths.append(str(c))


def _likely_windows_app_alias(path: str | Path) -> bool:
    s = str(path).replace("/", "\\").lower()
    return "\\windowsapps\\" in s


def python_probe(py: str) -> dict:
    if os.name == "nt" and _likely_windows_app_alias(py):
        return {"executable": py, "skipped": True, "reason": "Windows Store app execution alias, not a real Python environment"}
    code = r'''
import json, sys, importlib.util
info={"executable": sys.executable, "version": sys.version, "packages": {}}
for name in ["torch","qwen_asr","modelscope","opencc","transformers"]:
    info["packages"][name] = importlib.util.find_spec(name) is not None
try:
    import torch
    info["torch_version"] = torch.__version__
    info["cuda_available"] = bool(torch.cuda.is_available())
    info["cuda_device"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
except Exception as e:
    info["torch_error"] = repr(e)
print(json.dumps(info, ensure_ascii=False))
'''
    r = run_probe([py, "-c", code])
    if r.get("ok") and r.get("stdout"):
        try:
            return json.loads(r["stdout"].splitlines()[-1])
        except Exception:
            pass
    return {"executable": py, "probe_error": r}


def _python_patterns() -> list[Path]:
    if os.name == "nt":
        return [Path(".venv/Scripts/python.exe"), Path("venv/Scripts/python.exe"), Path("env/Scripts/python.exe")]
    return [Path(".venv/bin/python"), Path("venv/bin/python"), Path("env/bin/python")]


def scan_existing_pythons(
    root: str | Path,
    *,
    max_depth: int = DEFAULT_SCAN_MAX_DEPTH,
    max_dirs: int = DEFAULT_SCAN_MAX_DIRS,
    timeout_seconds: int = DEFAULT_SCAN_TIMEOUT_SECONDS,
) -> tuple[list[Path], dict]:
    """Bounded virtualenv discovery.

    Do not use unbounded ** globbing here: workspace roots may contain node_modules,
    generated media, network mounts, or permission-sensitive directories. os.walk with
    followlinks=False gives us pruning, limits, and a clean timeout path.
    """
    root_path = Path(root)
    started = time.monotonic()
    found: list[Path] = []
    scanned_dirs = 0
    skipped_dirs = 0
    errors: list[str] = []
    stopped_reason = None
    if not root_path.exists():
        return found, {"root": str(root_path), "exists": False, "error": "scan root does not exist"}
    root_depth = len(root_path.resolve().parts)
    patterns = _python_patterns()
    try:
        walker = os.walk(root_path, topdown=True, onerror=lambda e: errors.append(repr(e)), followlinks=False)
        for current, dirs, _files in walker:
            now = time.monotonic()
            if now - started > timeout_seconds:
                stopped_reason = "timeout"
                break
            scanned_dirs += 1
            if scanned_dirs > max_dirs:
                stopped_reason = "max_dirs"
                break
            current_path = Path(current)
            try:
                depth = len(current_path.resolve().parts) - root_depth
            except Exception:
                depth = max_depth + 1
            pruned: list[str] = []
            for d in list(dirs):
                if d in SKIP_SCAN_DIRS:
                    skipped_dirs += 1
                    continue
                if depth + 1 > max_depth:
                    skipped_dirs += 1
                    continue
                child = current_path / d
                try:
                    if child.is_symlink():
                        skipped_dirs += 1
                        continue
                except OSError:
                    skipped_dirs += 1
                    continue
                pruned.append(d)
            dirs[:] = pruned
            for pat in patterns:
                candidate = current_path / pat
                try:
                    if candidate.exists():
                        found.append(candidate)
                except OSError as e:
                    errors.append(repr(e))
    except Exception as e:
        errors.append(repr(e))
    return found, {
        "root": str(root_path),
        "exists": True,
        "scanned_dirs": scanned_dirs,
        "skipped_dirs": skipped_dirs,
        "found": len(found),
        "max_depth": max_depth,
        "max_dirs": max_dirs,
        "timeout_seconds": timeout_seconds,
        "stopped_reason": stopped_reason,
        "errors": errors[:8],
    }


def find_pythons(home: Path | None = None, extra_python: str | None = None, scan_roots: list[str] | None = None) -> tuple[list[str], list[dict]]:
    found: list[str] = []
    seen: set[str] = set()
    scan_reports: list[dict] = []
    if extra_python:
        _add_unique(found, seen, extra_python)
    names = ["python", "python3", "py"] if os.name != "nt" else ["python.exe", "python3.exe", "py.exe"]
    for n in names:
        p = shutil.which(n)
        if p:
            _add_unique(found, seen, p)
    home = home or default_home()
    candidates = [
        home / "envs" / "qwen-local" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"),
        home / "env" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"),
    ]
    for root in scan_roots or []:
        scan_found, scan_report = scan_existing_pythons(root)
        candidates.extend(scan_found)
        scan_reports.append(scan_report)
    for c in candidates:
        _add_unique(found, seen, c)
    return found, scan_reports


def _nvidia_smi_candidates() -> list[str]:
    candidates: list[str] = []
    p = shutil.which("nvidia-smi") or shutil.which("nvidia-smi.exe")
    if p:
        candidates.append(p)
    if os.name == "nt":
        program_files = [os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432")]
        for base in program_files:
            if base:
                candidates.append(str(Path(base) / "NVIDIA Corporation" / "NVSMI" / "nvidia-smi.exe"))
    seen: set[str] = set()
    unique: list[str] = []
    for c in candidates:
        if Path(c).exists():
            key = _same_path_key(c)
            if key not in seen:
                seen.add(key)
                unique.append(c)
    return unique


def _parse_nvidia_smi_csv(stdout: str) -> list[dict]:
    gpus = []
    for line in stdout.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 3:
            gpus.append({"name": parts[0], "driver_version": parts[1], "memory_total": parts[2]})
        elif line.strip():
            gpus.append({"raw": line.strip()})
    return gpus


def _windows_gpu_names() -> dict:
    if os.name != "nt":
        return {"ok": False, "names": []}
    ps = shutil.which("powershell") or shutil.which("powershell.exe")
    if not ps:
        return {"ok": False, "names": [], "error": "powershell not found"}
    r = run_probe([ps, "-NoProfile", "-Command", "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"], timeout=15)
    names = [line.strip() for line in (r.get("stdout") or "").splitlines() if line.strip()]
    return {"ok": bool(names), "names": names, "probe": r}


def detect_gpu() -> dict:
    cim = _windows_gpu_names() if os.name == "nt" else {"ok": False, "names": []}
    for nvidia_smi in _nvidia_smi_candidates():
        r = run_probe([nvidia_smi, "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"], timeout=10)
        if r.get("ok") and r.get("stdout"):
            return {"type": "nvidia", "method": "nvidia-smi", "path": nvidia_smi, "gpus": _parse_nvidia_smi_csv(r["stdout"]), "windows_names": cim.get("names", []), **r}
    names = cim.get("names", [])
    if names:
        lowered = [n.lower() for n in names]
        if any("nvidia" in n or "geforce" in n or "quadro" in n or "rtx" in n or "gtx" in n for n in lowered):
            gpu_type = "nvidia"
        elif any("amd" in n or "radeon" in n for n in lowered):
            gpu_type = "amd"
        elif any("intel" in n or "iris" in n or "uhd" in n for n in lowered):
            gpu_type = "intel"
        else:
            gpu_type = "other"
        return {"type": gpu_type, "method": "windows-cim", "ok": True, "names": names, "nvidia_smi_found": bool(_nvidia_smi_candidates())}
    return {"type": "unknown", "ok": False, "error": "no GPU detector found or no GPU detected"}


def _probe_unique_pythons(python_paths: list[str]) -> list[dict]:
    probes: list[dict] = []
    seen: set[str] = set()
    for path in python_paths:
        probe = python_probe(path)
        key = probe.get("executable") or path
        key = str(key).casefold() if os.name == "nt" else str(key)
        if key in seen:
            continue
        seen.add(key)
        probes.append(probe)
    return probes


def _yes_no(value: bool) -> str:
    return "已安装" if value else "未安装"


def _gpu_label(gpu: dict) -> str:
    if not gpu:
        return "未检测到"
    if gpu.get("type") == "nvidia" and gpu.get("gpus"):
        return " / ".join(g.get("name") or g.get("raw") or "NVIDIA" for g in gpu.get("gpus", []))
    names = gpu.get("names") or gpu.get("windows_names") or []
    if names:
        return " / ".join(names)
    return gpu.get("type") or "未检测到"


def print_healthcheck_summary(report: dict) -> None:
    models = report.get("models") or {}
    print("先检查一下电脑环境：Python、ffmpeg、显卡、模型目录。这一步不会安装或下载东西。")
    print("\n检查完成：")
    print(f"- ffmpeg：{_yes_no(bool((report.get('ffmpeg') or {}).get('found')))}")
    print(f"- ffprobe：{_yes_no(bool((report.get('ffprobe') or {}).get('found')))}")
    print(f"- 显卡：{_gpu_label(report.get('gpu') or {})}")
    print(f"- Qwen 高质量模型：{_yes_no(bool(models.get('qwen_asr_best')))}")
    print(f"- Qwen 小模型：{_yes_no(bool(models.get('qwen_asr_small')))}")
    print(f"- 对齐模型：{_yes_no(bool(models.get('qwen_aligner')))}")
    print(f"- 模型目录：{report.get('home')}")
    gpu_type = (report.get("gpu") or {}).get("type")
    if gpu_type != "nvidia":
        print("\n提醒：没有检测到已验证的 NVIDIA/CUDA 快速路径，后面可能会跑得比较慢。建议先用 30-60 秒样片 smoke-test。")
    print("\n下一步：运行 setup-plan 查看安装方案。")


def print_setup_plan_summary(plan: dict) -> None:
    qwen = plan.get("qwen_local") or {}
    model_policy = plan.get("model_policy") or {}
    missing = plan.get("missing") or []
    selected = qwen.get("selected_asr_model") or "Qwen3-ASR-1.7B"
    aligner = qwen.get("aligner_model") or "Qwen3-ForcedAligner-0.6B"
    print("安装方案检查完成：")
    print(f"- 字幕模型：{selected}")
    print(f"- 对齐模型：{aligner}")
    print(f"- 安装位置：{plan.get('home')}")
    print(f"- 当前选择：{model_policy.get('selected_tier', 'best')}（默认先追求质量；测试太慢再降级 small）")
    if not missing:
        print("\n当前环境已满足要求，无需重复安装或下载。")
    else:
        print("\n需要补齐：")
        for item in missing:
            print(f"- {item.get('label')}: {item.get('detail')}")
        print("\n这一步只是计划，没有安装或下载。")
        print("下一步 setup 只会补齐上面缺失的部分；执行前需要确认。")


def healthcheck(args) -> dict:
    home = Path(args.home) if args.home else default_home()
    ffmpeg = find_tool_binary("ffmpeg", home=home)
    gpu = detect_gpu()
    scan_roots = getattr(args, "scan_root", None) or []
    python_paths, scan_reports = find_pythons(home=home, extra_python=getattr(args, "python", None), scan_roots=scan_roots)
    pythons = _probe_unique_pythons(python_paths)
    model_base = _default_models_dir(home)
    ffprobe = find_tool_binary("ffprobe", home=home)
    models = {
        "qwen_asr_best": (model_base / "Qwen3-ASR-1.7B" / "model.safetensors").exists(),
        "qwen_asr_small": (model_base / "Qwen3-ASR-0.6B" / "model.safetensors").exists(),
        "qwen_aligner": (model_base / "Qwen3-ForcedAligner-0.6B" / "model.safetensors").exists(),
    }
    report = {
        "skill": "lzp-video-subtitle",
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine(), "python_current": sys.executable},
        "home": str(home),
        "paths": {"skill_root": str(SKILL_ROOT), "home_exists": home.exists(), "home_writable_parent": os.access(str(home.parent if home.parent.exists() else Path.home()), os.W_OK), "models_dir": str(model_base)},
        "ffmpeg": {"found": bool(ffmpeg), "path": ffmpeg},
        "ffprobe": {"found": bool(ffprobe), "path": ffprobe},
        "gpu": gpu,
        "scan_roots": scan_reports,
        "pythons": pythons,
        "models": models,
        "notes": [
            "Default healthcheck does not scan whole disks or network shares.",
            "Use --python to test a known environment; use --scan-root for bounded existing-venv discovery.",
            "ffmpeg lookup order: explicit env path, skill/tools, runtime/tools, then PATH.",
            "ffprobe is recommended for duration/RTF metrics but is not required for subtitle generation.",
            "Models default to <home>/models/qwen after command --home is resolved; override with VIDEO_SUBTITLE_MODELS_DIR / LZP_VIDEO_SUBTITLE_MODELS_DIR / QWEN_SUBTITLE_MODELS if needed.",
            "--scan-root is bounded by depth, directory count, timeout, symlink skipping, and common heavy-directory pruning.",
            "Custom homes, including NAS/network paths, are allowed but must pass healthcheck/smoke tests.",
        ],
    }
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if not getattr(args, "quiet", False):
            print(f"检查报告已写入：{args.json}")
    elif not getattr(args, "quiet", False):
        print_healthcheck_summary(report)
    return report


def setup_plan(args) -> dict:
    report = healthcheck(argparse.Namespace(home=args.home, json=None, python=getattr(args, "python", None), scan_root=getattr(args, "scan_root", None) or [], quiet=True))
    gpu = report.get("gpu") or {}
    gpu_type = gpu.get("type")
    system = (report.get("platform") or {}).get("system")
    has_nvidia = gpu_type == "nvidia"
    model_tier = getattr(args, "model_tier", None) or "best"
    model_catalog = {
        "best": {
            "asr_model": "Qwen3-ASR-1.7B",
            "role": "default quality-first ASR model",
            "fallback_to": "small",
            "warning": "Best quality path; requires more compute/memory. Run smoke-test before batch jobs.",
        },
        "small": {
            "asr_model": "Qwen3-ASR-0.6B",
            "role": "lightweight fallback ASR model",
            "fallback_to": None,
            "warning": "Efficiency path; use when best is too slow or fails smoke-test.",
        },
    }
    selected_model = model_catalog[model_tier]
    selected_asr_key = "qwen_asr_best" if model_tier == "best" else "qwen_asr_small"
    selected_asr_ready = bool((report.get("models") or {}).get(selected_asr_key))
    aligner_ready = bool((report.get("models") or {}).get("qwen_aligner"))
    qwen_env_probe = next(
        (
            p for p in report["pythons"]
            if p.get("packages", {}).get("torch") and p.get("packages", {}).get("qwen_asr") and p.get("packages", {}).get("modelscope")
        ),
        None,
    )
    qwen_env_ready = bool(qwen_env_probe)
    qwen_cuda_ready = any(
        p.get("packages", {}).get("torch") and p.get("cuda_available")
        for p in report["pythons"]
    )
    missing = []
    warnings = []
    if not (report.get("ffmpeg") or {}).get("found"):
        missing.append({
            "type": "binary",
            "label": "ffmpeg",
            "detail": "未检测到 ffmpeg；需要用于音频抽取和 smoke-test 截取样片。可通过 PATH、skill/tools 或 runtime/tools 提供。",
        })
    if not (report.get("ffprobe") or {}).get("found"):
        warnings.append("ffprobe not detected: sample duration / RTF may be unavailable; ffmpeg fallback will be attempted where possible.")
    if not qwen_env_ready:
        missing.append({
            "type": "python_env",
            "label": "Qwen Python 运行环境",
            "detail": "缺少同时包含 torch / qwen_asr / modelscope 的 Python 环境",
            "packages": ["torch", "qwen-asr", "modelscope", "transformers", "accelerate", "librosa", "soundfile"],
        })
    if has_nvidia and qwen_env_ready and not qwen_cuda_ready:
        missing.append({
            "type": "cuda_torch",
            "label": "CUDA 版 PyTorch",
            "detail": "已检测到 NVIDIA 显卡，也找到了 Qwen Python 环境，但该环境 torch.cuda.is_available() 为 false；需要安装/修复 CUDA 版 PyTorch",
            "package": "torch",
            "default_index_url": "https://download.pytorch.org/whl/cu121",
            "override_env": ["LZP_TORCH_INDEX_URL", "VIDEO_SUBTITLE_TORCH_INDEX_URL"],
        })
    if not selected_asr_ready:
        missing.append({
            "type": "model",
            "model_role": "asr",
            "label": f"字幕模型 {selected_model['asr_model']}",
            "detail": f"模型目录中未检测到 {selected_model['asr_model']}",
            "model_id": f"Qwen/{selected_model['asr_model']}",
        })
    if not aligner_ready:
        missing.append({
            "type": "model",
            "model_role": "aligner",
            "label": "对齐模型 Qwen3-ForcedAligner-0.6B",
            "detail": "模型目录中未检测到 Qwen3-ForcedAligner-0.6B",
            "model_id": "Qwen/Qwen3-ForcedAligner-0.6B",
        })
    warnings.extend([
        "This skill is a Qwen local subtitle workflow. It does not auto-switch to Whisper based on hardware.",
        "Default ASR tier is best (Qwen3-ASR-1.7B). If smoke-test is too slow or fails, downgrade to small (Qwen3-ASR-0.6B).",
        "Qwen local runs large local models; machines without a validated GPU fast path may be slow or need platform-specific PyTorch setup.",
    ])
    if has_nvidia:
        hardware_status = "validated-fast-path"
        warnings.append("NVIDIA/CUDA detected: this is the currently validated fast path for Qwen local.")
    elif gpu_type == "amd":
        hardware_status = "unvalidated-amd"
        warnings.append("AMD GPU detected: Qwen is not ruled out, but this skill has not validated AMD acceleration; expect smoke tests and possible slow CPU fallback.")
    elif gpu_type in {"intel", "other", "unknown", None}:
        hardware_status = "unvalidated-or-cpu"
        warnings.append("No validated NVIDIA/CUDA fast path detected; Qwen may still run but speed can be significantly worse.")
    else:
        hardware_status = "unvalidated"
        warnings.append(f"GPU type {gpu_type!r} is not validated by this skill yet; proceed with smoke tests.")
    plan = {
        "home": report["home"],
        "paths": report.get("paths") or {},
        "safe": "No install/download has been performed. Run setup explicitly after reviewing requirements and warnings.",
        "product_backend": "qwen-local",
        "backend_policy": "fixed-qwen-local; hardware affects warnings/feasibility, not automatic model selection",
        "model_policy": {
            "default_tier": "best",
            "selected_tier": model_tier,
            "tiers": model_catalog,
            "aligner_model": "Qwen3-ForcedAligner-0.6B",
            "downgrade_rule": "Run smoke-test on best first; downgrade to small only if best is too slow, fails, or exceeds memory limits.",
        },
        "detected_hardware": {"system": system, "gpu_type": gpu_type, "gpu": gpu, "status": hardware_status},
        "qwen_local": {
            "recommended": True,
            "env_ready": qwen_env_ready,
            "env_python": qwen_env_probe.get("executable") if qwen_env_probe else None,
            "cuda_ready": qwen_cuda_ready,
            "cuda_required": has_nvidia,
            "selected_asr_model": selected_model["asr_model"],
            "aligner_model": "Qwen3-ForcedAligner-0.6B",
            "downloads": [item for item in missing if item.get("type") == "model"],
            "warnings": warnings,
        },
        "profile_policy": {
            "recommended": "Create one profile per teacher, long-running course, or major project.",
            "profile_home": str(Path(report["home"]) / "profiles" / "<profile>"),
            "feedback_rule": "Manual corrections from edited subtitles are learned into the profile, not into a single video output directory.",
        },
        "output_contract": {
            "standard": ["final.srt", "final.txt", "review_focus.csv"],
            "final_txt": "Pure readable text only: no timecodes, no SRT indexes, no subtitle formatting.",
            "debug_optional": ["debug/run_report.json", "debug/asr_text_raw.txt", "debug/asr_text_clean.txt", "debug/align_items.json"],
        },
        "smoke_test_policy": {
            "sample_duration_seconds": "30-60",
            "reports": ["success/failure", "processing_time", "RTF", "execution_path", "memory/OOM errors", "recommendation"],
            "possible_recommendations": ["keep best", "downgrade to small", "fix environment", "use stronger machine"],
        },
        "missing": missing,
        "setup_actions": [
            "none; environment is already ready" if not missing else "install only missing items listed in missing[]"
        ],
        "next_commands": [
            "lzp-video-subtitle init-profile --profile <teacher-or-project>",
            f"lzp-video-subtitle setup --backend qwen-local --model-tier {model_tier} --home <path>",
            f"lzp-video-subtitle smoke-test --backend qwen-local --model-tier {model_tier} --input <short-sample>",
            "lzp-video-subtitle run --profile <profile> --input <video>",
            "lzp-video-subtitle learn --profile <profile> --raw <output/final.srt> --edited <path/to/edited.srt>",        ],
    }
    if args.json:
        Path(args.json).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        if not getattr(args, "quiet", False):
            print(f"安装方案已写入：{args.json}")
    elif not getattr(args, "quiet", False):
        print_setup_plan_summary(plan)
    return plan


def init_profile(args) -> dict:
    home = Path(args.home) if args.home else default_home()
    profile_dir = home / "profiles" / args.profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "lexicon.csv": "term,reading,notes\n",
        "protected_terms.csv": "term,category,notes\n",
        "corrections.csv": "wrong,correct,notes\n",
        "style_rules.yml": "# 字幕风格规则\nline_max_chars: null\nmax_lines: null\nnotes: []\n",
        "feedback_log.jsonl": "",
    }
    created = []
    kept = []
    for name, content in files.items():
        path = profile_dir / name
        if path.exists():
            kept.append(name)
            continue
        path.write_text(content, encoding="utf-8")
        created.append(name)
    result = {"profile": args.profile, "profile_dir": str(profile_dir), "created": created, "kept_existing": kept}
    print(f"词库已准备好：{profile_dir}")
    if created:
        print("新建文件：" + "、".join(created))
    if kept:
        print("已存在，未覆盖：" + "、".join(kept))
    print("后续同一位老师/项目的视频都建议使用这个 profile，避免词库混用。")
    return result


def _workspace_root() -> Path:
    # skills/<skill-name>/scripts -> workspace
    return SKILL_ROOT.parent.parent


def _default_models_dir(home: Path | None = None) -> Path:
    env_models = os.environ.get("VIDEO_SUBTITLE_MODELS_DIR") or os.environ.get("LZP_VIDEO_SUBTITLE_MODELS_DIR") or os.environ.get("QWEN_SUBTITLE_MODELS")
    if env_models:
        return Path(env_models)
    return (home or default_home()) / "models" / "qwen"


def _asr_model_id(model_tier: str) -> str:
    return "Qwen/Qwen3-ASR-1.7B" if model_tier == "best" else "Qwen/Qwen3-ASR-0.6B"


def _model_dir_name(model_id: str) -> str:
    return model_id.rstrip("/").split("/")[-1]


def _qwen_python_candidates(home: Path | None = None, extra_python: str | None = None) -> list[str]:
    workspace = _workspace_root()
    home = home or default_home()
    candidates: list[str] = []
    seen: set[str] = set()
    common = []
    if os.name == "nt":
        common.extend([
            home / "envs" / "qwen-local" / "Scripts" / "python.exe",
            workspace / ".venv" / "Scripts" / "python.exe",
        ])
    else:
        common.extend([
            home / "envs" / "qwen-local" / "bin" / "python",
            workspace / ".venv" / "bin" / "python",
        ])
    if extra_python:
        _add_unique(candidates, seen, extra_python)
    for c in common:
        _add_unique(candidates, seen, c)
    for py in find_pythons(home=home, extra_python=None, scan_roots=[])[0]:
        _add_unique(candidates, seen, py)
    return candidates


def _select_qwen_python(home: Path | None = None, extra_python: str | None = None) -> str:
    failures: list[str] = []
    for py in _qwen_python_candidates(home=home, extra_python=extra_python):
        probe = python_probe(py)
        packages = probe.get("packages") or {}
        if packages.get("torch") and packages.get("qwen_asr") and packages.get("modelscope"):
            return str(probe.get("executable") or py)
        failures.append(f"{py}: qwen_asr={packages.get('qwen_asr')} torch={packages.get('torch')} modelscope={packages.get('modelscope')} opencc={packages.get('opencc')}")
    detail = "\n".join(failures[:8]) if failures else "未找到可用 Python。"
    raise RuntimeError(
        "没有找到已安装 qwen_asr / torch / modelscope 的 Python 环境。\n"
        "请先完成 setup，或用 --python 指定可用虚拟环境。\n"
        f"已检查：\n{detail}"
    )


def _runtime_env_python(home: Path) -> Path:
    if os.name == "nt":
        return home / "envs" / "qwen-local" / "Scripts" / "python.exe"
    return home / "envs" / "qwen-local" / "bin" / "python"


def _install_cuda_torch(env_python: str | Path) -> dict:
    gpu = detect_gpu()
    has_nvidia = gpu.get("type") == "nvidia"
    if not has_nvidia:
        return {"skipped": True, "reason": "no NVIDIA GPU detected", "gpu": gpu}
    torch_index_url = os.environ.get("LZP_TORCH_INDEX_URL") or os.environ.get("VIDEO_SUBTITLE_TORCH_INDEX_URL") or "https://download.pytorch.org/whl/cu121"
    print(f"检测到 NVIDIA 显卡，安装 / 修复 CUDA 版 PyTorch：{torch_index_url}")
    subprocess.run([str(env_python), "-m", "pip", "install", "--upgrade", "torch", "--index-url", torch_index_url], check=True)
    probe = python_probe(str(env_python))
    if not probe.get("cuda_available"):
        raise RuntimeError(
            "检测到 NVIDIA 显卡，但安装后的 PyTorch 仍不可用 CUDA。\n"
            f"torch_version={probe.get('torch_version')} cuda_available={probe.get('cuda_available')} torch_error={probe.get('torch_error')}\n"
            "请确认 NVIDIA 驱动正常，或通过 LZP_TORCH_INDEX_URL / VIDEO_SUBTITLE_TORCH_INDEX_URL 指定匹配的 PyTorch CUDA wheel index 后重试。"
        )
    return {"skipped": False, "index_url": torch_index_url, "probe": probe}


def _create_or_update_qwen_env(home: Path) -> str:
    env_python = _runtime_env_python(home)
    env_dir = env_python.parent.parent
    if not env_python.exists():
        print(f"创建 Qwen 运行环境：{env_dir}")
        subprocess.run([sys.executable, "-m", "venv", str(env_dir)], check=True)
    packages = [
        "--upgrade",
        "pip",
        "setuptools",
        "wheel",
    ]
    subprocess.run([str(env_python), "-m", "pip", "install", *packages], check=True)
    cuda_torch_result = _install_cuda_torch(env_python)
    required = [
        "qwen-asr",
        "modelscope",
        "transformers",
        "accelerate",
        "librosa",
        "soundfile",
        "qwen-omni-utils",
    ]
    print("安装 / 更新 Qwen 字幕依赖：" + "、".join(required))
    subprocess.run([str(env_python), "-m", "pip", "install", *required], check=True)
    if cuda_torch_result.get("skipped"):
        subprocess.run([str(env_python), "-m", "pip", "install", "--upgrade", "torch"], check=True)
    probe = python_probe(str(env_python))
    packages_probe = probe.get("packages") or {}
    if not (packages_probe.get("torch") and packages_probe.get("qwen_asr") and packages_probe.get("modelscope")):
        raise RuntimeError(f"Qwen 运行环境安装后仍未通过检查：{probe}")
    return str(probe.get("executable") or env_python)


def _download_missing_models(py: str, models_dir: Path, model_ids: list[str]) -> None:
    if not model_ids:
        return
    models_dir.mkdir(parents=True, exist_ok=True)
    code = """
from modelscope import snapshot_download
from pathlib import Path
import sys
models_dir = Path(sys.argv[1])
for model_id in sys.argv[2:]:
    local_dir = models_dir / model_id.rstrip('/').split('/')[-1]
    if (local_dir / 'model.safetensors').exists():
        print(f'已存在：{local_dir}')
    else:
        print(f'开始下载：{model_id} -> {local_dir}')
        snapshot_download(model_id, local_dir=str(local_dir))
""".strip()
    subprocess.run([py, "-c", code, str(models_dir), *model_ids], check=True)


def _runner_config(
    *,
    input_path: Path,
    output_dir: Path,
    profile: str,
    home: Path,
    model_tier: str,
    prefer_cuda: bool = True,
) -> dict:
    return {
        "video_path": str(input_path.resolve()),
        "output_dir": str(output_dir.resolve()),
        "project_lexicon": str((home / "profiles" / profile / "corrections.csv").resolve()),
        "asr_model": _asr_model_id(model_tier),
        "aligner_model": "Qwen/Qwen3-ForcedAligner-0.6B",
        "prefer_cuda": bool(prefer_cuda),
        "language": "Chinese",
        "max_chars": 14,
        "min_duration": 1.0,
        "hard_min_duration": 0.6,
    }


def _call_qwen_runner(config: dict, *, work_dir: Path | None = None, models_dir: Path | None = None, python_executable: str | None = None, numba_cache_dir: Path | None = None) -> None:
    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    debug_dir = output_dir / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    config_path = debug_dir / "lzp_run_config.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    env = os.environ.copy()
    resolved_models_dir = models_dir or _default_models_dir()
    env.setdefault("QWEN_SUBTITLE_MODELS", str(resolved_models_dir.resolve()))
    resolved_numba_cache = numba_cache_dir or (Path(config["output_dir"]).parent / "numba_cache")
    resolved_numba_cache.mkdir(parents=True, exist_ok=True)
    env.setdefault("NUMBA_CACHE_DIR", str(resolved_numba_cache.resolve()))
    if work_dir:
        work_dir.mkdir(parents=True, exist_ok=True)
        env["QWEN_SUBTITLE_WORK"] = str(work_dir.resolve())
    runner = SKILL_ROOT / "scripts" / "video_subtitle_run.py"
    py = python_executable or _select_qwen_python()
    subprocess.run([py, str(runner), "--config", str(config_path)], check=True, env=env, text=True, encoding="utf-8", errors="replace")


def _probe_audio_duration_seconds(path: Path, *, home: Path | None = None) -> tuple[float | None, list[str]]:
    warnings: list[str] = []
    ffprobe = find_tool_binary("ffprobe", home=home)
    if ffprobe:
        r = run_probe([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)], timeout=20)
        if r.get("ok") and r.get("stdout"):
            try:
                return float(str(r["stdout"]).splitlines()[-1].strip()), warnings
            except Exception as e:
                warnings.append(f"ffprobe returned unparseable duration: {e!r}; trying ffmpeg fallback.")
        else:
            warnings.append("ffprobe duration probe failed; trying ffmpeg fallback.")
    else:
        warnings.append("ffprobe not found; trying ffmpeg fallback for duration. Subtitle generation can still succeed without ffprobe.")
    ffmpeg = find_tool_binary("ffmpeg", home=home)
    if not ffmpeg:
        warnings.append("ffmpeg not found; sample_duration and rtf are unavailable.")
        return None, warnings
    r = run_probe([ffmpeg, "-i", str(path)], timeout=20)
    text = "\n".join([str(r.get("stderr") or ""), str(r.get("stdout") or "")])
    import re
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not m:
        warnings.append("Could not parse duration from ffmpeg output; sample_duration and rtf are unavailable.")
        return None, warnings
    try:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)), warnings
    except Exception as e:
        warnings.append(f"Could not parse ffmpeg duration fields: {e!r}; sample_duration and rtf are unavailable.")
        return None, warnings


def _probe_audio_duration_value(path: Path, *, home: Path | None = None) -> float | None:
    duration, _warnings = _probe_audio_duration_seconds(path, home=home)
    return duration


def _extract_smoke_sample(input_path: Path, sample_path: Path, seconds: int = 60, *, home: Path | None = None) -> Path:
    duration = _probe_audio_duration_value(input_path, home=home)
    if duration is not None and duration <= seconds + 3:
        return input_path
    ffmpeg = find_tool_binary("ffmpeg", home=home)
    if not ffmpeg:
        raise RuntimeError("需要截取 60 秒样片，但没有找到 ffmpeg。请先安装 ffmpeg、把便携 ffmpeg 放到 skill/tools 或 runtime/tools，或提供 30-60 秒短样片。")
    sample_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, "-y", "-i", str(input_path), "-t", str(seconds), "-c", "copy", str(sample_path)], check=True, text=True, encoding="utf-8", errors="replace", capture_output=True)
    return sample_path


def _smoke_recommendation(ok: bool, duration: float | None, elapsed: float, model_tier: str, error: str | None = None) -> str:
    if not ok:
        if error and ("out of memory" in error.lower() or "cuda" in error.lower()):
            return "install_or_enable_small" if model_tier == "best" else "fix_environment"
        return "fix_environment"
    if duration and duration > 0:
        rtf = elapsed / duration
        if model_tier == "best" and rtf > 2.5:
            return "install_or_enable_small"
        if rtf > 5:
            return "use_stronger_machine"
    return "keep_best" if model_tier == "best" else "keep_small"


def state_dir(home: Path) -> Path:
    return home / "state"


def write_current_state(home: Path, data: dict) -> None:
    d = state_dir(home)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "current.json"
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    existing.update(data)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def default_output_dir_for_video(input_path: str | Path) -> Path:
    p = Path(input_path)
    return p.parent / f"{p.stem}_subtitle"


def _write_placeholder_outputs(output_dir: Path, input_path: Path, profile: str, *, debug_artifacts: bool = False) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "final.srt").write_text("", encoding="utf-8")
    (output_dir / "final.txt").write_text("", encoding="utf-8")
    (output_dir / "review_focus.csv").write_text("idx,start,end,duration,text,risk,reason\n", encoding="utf-8")
    if debug_artifacts:
        debug = output_dir / "debug"
        debug.mkdir(exist_ok=True)
        (debug / "run_report.json").write_text(json.dumps({"input": str(input_path), "profile": profile, "status": "placeholder"}, ensure_ascii=False, indent=2), encoding="utf-8")


def run_command(args) -> dict:
    home = Path(args.home) if args.home else default_home()
    input_path = Path(args.input)
    output_dir = Path(args.output_dir) if args.output_dir else default_output_dir_for_video(input_path)
    model_tier = getattr(args, "model_tier", "small")
    py = _select_qwen_python(home=home, extra_python=getattr(args, "python", None))
    cfg = _runner_config(input_path=input_path, output_dir=output_dir, profile=args.profile, home=home, model_tier=model_tier, prefer_cuda=not getattr(args, "cpu", False))
    _call_qwen_runner(cfg, work_dir=home / "work" / output_dir.name, models_dir=_default_models_dir(home), python_executable=py, numba_cache_dir=home / "numba_cache")
    result = {
        "stage": "subtitle_generated",
        "active_profile": args.profile,
        "model_tier": model_tier,
        "last_input": str(input_path),
        "last_output_dir": str(output_dir),
        "generated_files": ["final.srt", "final.txt", "review_focus.csv"],
        "next_entry": "/lzp-video-subtitle-learn",
        "status": "generated",
    }
    write_current_state(home, result)
    print("字幕生成完成。")
    print(f"输出目录：{output_dir}")
    print("已生成：final.srt、final.txt、review_focus.csv")
    print("请先人工检查 final.srt / final.txt，尤其是 review_focus.csv 标记的位置。")
    print("如果你修改了字幕，请重新导出另存一份 srt 文件，这非常重要。")
    print("下一步可以进入 `/lzp-video-subtitle-learn`，我会把你确认过的修正沉淀到词库。")
    return result


def batch_command(args) -> dict:
    home = Path(args.home) if args.home else default_home()
    input_dir = Path(args.input_dir)
    exts = {".mp4", ".mov", ".m4v", ".mp3", ".wav", ".m4a", ".aac", ".flac"}
    files = [p for p in sorted(input_dir.iterdir()) if p.is_file() and p.suffix.lower() in exts] if input_dir.exists() else []
    model_tier = getattr(args, "model_tier", "small")
    py = _select_qwen_python(home=home, extra_python=getattr(args, "python", None))
    outputs = []
    for p in files:
        out = default_output_dir_for_video(p)
        cfg = _runner_config(input_path=p, output_dir=out, profile=args.profile, home=home, model_tier=model_tier, prefer_cuda=not getattr(args, "cpu", False))
        _call_qwen_runner(cfg, work_dir=home / "work" / out.name, models_dir=_default_models_dir(home), python_executable=py, numba_cache_dir=home / "numba_cache")
        outputs.append({"input": str(p), "output_dir": str(out)})
    result = {
        "stage": "subtitle_generated",
        "active_profile": args.profile,
        "model_tier": model_tier,
        "last_input_dir": str(input_dir),
        "batch_count": len(outputs),
        "outputs": outputs,
        "next_entry": "/lzp-video-subtitle-learn",
        "status": "generated",
    }
    write_current_state(home, result)
    print(f"批量字幕生成完成：{len(outputs)} 个视频/音频。")
    for item in outputs[:10]:
        print(f"- {item['input']} -> {item['output_dir']}")
    if len(outputs) > 10:
        print(f"... 还有 {len(outputs)-10} 个文件")
    return result


def _read_srt_text(path: Path) -> str:
    lines = []
    for raw in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.isdigit():
            continue
        if "-->" in line:
            continue
        lines.append(line)
    return "\n".join(lines)


def _common_prefix_len(a: str, b: str) -> int:
    i = 0
    max_i = min(len(a), len(b))
    while i < max_i and a[i] == b[i]:
        i += 1
    return i


def _common_suffix_len(a: str, b: str, prefix_len: int) -> int:
    i = 0
    max_i = min(len(a), len(b)) - prefix_len
    while i < max_i and a[len(a) - 1 - i] == b[len(b) - 1 - i]:
        i += 1
    return i


def _diff_lines_to_candidates(raw_text: str, edited_text: str) -> list[dict]:
    raw_lines = [x.strip() for x in raw_text.splitlines() if x.strip()]
    edited_lines = [x.strip() for x in edited_text.splitlines() if x.strip()]
    candidates: list[dict] = []

    def is_cjk(ch: str) -> bool:
        return "\u4e00" <= ch <= "\u9fff"

    def expand_tiny_cjk_diff(raw_line: str, edited_line: str, pre: int, suf: int) -> tuple[str, str, str]:
        raw_end = len(raw_line) - suf if suf else len(raw_line)
        edited_end = len(edited_line) - suf if suf else len(edited_line)
        wrong = raw_line[pre:raw_end].strip()
        correct = edited_line[pre:edited_end].strip()
        note = ""
        # 单字差异通常不是好词库项；向左吃一个中文字符，把“贤→衔”提升为“陈贤→陈衔”。
        if len(wrong) == 1 and len(correct) == 1 and pre > 0 and is_cjk(raw_line[pre - 1]) and is_cjk(edited_line[pre - 1]):
            pre -= 1
            wrong = raw_line[pre:raw_end].strip()
            correct = edited_line[pre:edited_end].strip()
            note = ";expanded_cjk_left"
        return wrong, correct, note

    for idx, (raw_line, edited_line) in enumerate(zip(raw_lines, edited_lines), 1):
        if raw_line == edited_line:
            continue
        pre = _common_prefix_len(raw_line, edited_line)
        suf = _common_suffix_len(raw_line, edited_line, pre)
        wrong, correct, extra_note = expand_tiny_cjk_diff(raw_line, edited_line, pre, suf)
        if wrong and correct and wrong != correct and len(wrong) <= 40 and len(correct) <= 40:
            candidates.append({"wrong": wrong, "correct": correct, "notes": f"line:{idx}{extra_note}"})
    if len(raw_lines) != len(edited_lines) or not candidates:
        # Conservative fallback: whole-line candidates only when they are short enough.
        for idx, (raw_line, edited_line) in enumerate(zip(raw_lines, edited_lines), 1):
            if raw_line != edited_line and len(raw_line) <= 40 and len(edited_line) <= 40:
                item = {"wrong": raw_line, "correct": edited_line, "notes": f"line:{idx};whole_line"}
                if item not in candidates:
                    candidates.append(item)
    # de-duplicate while preserving order
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for c in candidates:
        key = (c["wrong"], c["correct"])
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def _append_confirmed_corrections(home: Path, profile: str, candidates_csv: Path) -> dict:
    profile_dir = home / "profiles" / profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    target = profile_dir / "corrections.csv"
    if not target.exists():
        target.write_text("wrong,correct,notes\n", encoding="utf-8")
    backup = target.with_name(f"corrections.backup-{time.strftime('%Y%m%d-%H%M%S')}.csv")
    shutil.copy2(target, backup)
    existing_pairs: set[tuple[str, str]] = set()
    with target.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            existing_pairs.add(((row.get("wrong") or "").strip(), (row.get("correct") or "").strip()))
    added = 0
    with candidates_csv.open("r", encoding="utf-8-sig", newline="") as src, target.open("a", encoding="utf-8-sig", newline="") as dst:
        reader = csv.DictReader(src)
        writer = csv.DictWriter(dst, fieldnames=["wrong", "correct", "notes"])
        for row in reader:
            wrong = (row.get("wrong") or "").strip()
            correct = (row.get("correct") or "").strip()
            notes = (row.get("notes") or "").strip()
            if not wrong or not correct or wrong == correct:
                continue
            key = (wrong, correct)
            if key in existing_pairs:
                continue
            writer.writerow({"wrong": wrong, "correct": correct, "notes": notes})
            existing_pairs.add(key)
            added += 1
    return {"added": added, "backup": str(backup), "target": str(target)}


def learn_command(args) -> dict:
    home = Path(args.home) if args.home else default_home()
    raw = Path(args.raw)
    edited = Path(args.edited)
    candidates_out = Path(args.candidates_out) if args.candidates_out else edited.with_name("learn_candidates.csv")
    candidates_out.parent.mkdir(parents=True, exist_ok=True)
    raw_text = _read_srt_text(raw) if raw.suffix.lower() == ".srt" else raw.read_text(encoding="utf-8-sig", errors="ignore")
    edited_text = _read_srt_text(edited) if edited.suffix.lower() == ".srt" else edited.read_text(encoding="utf-8-sig", errors="ignore")
    candidates = _diff_lines_to_candidates(raw_text, edited_text)
    with candidates_out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["wrong", "correct", "notes"])
        writer.writeheader()
        writer.writerows(candidates)
    write_result = None
    status = "candidates_created"
    if getattr(args, "confirm_write", False):
        write_result = _append_confirmed_corrections(home, args.profile, candidates_out)
        status = "profile_updated"
    result = {
        "stage": "learn_candidates_generated" if not write_result else "learn_profile_updated",
        "active_profile": args.profile,
        "last_raw": str(raw),
        "last_edited": str(edited),
        "candidates_out": str(candidates_out),
        "candidate_count": len(candidates),
        "write_result": write_result,
        "status": status,
    }
    write_current_state(home, result)
    print(f"找到 {len(candidates)} 条可学习内容。")
    print(f"候选文件：{candidates_out}")
    if write_result:
        print(f"已写入词库：{write_result['target']}")
        print(f"写入前备份：{write_result['backup']}")
    else:
        print("暂未写入词库。请人工检查候选文件；确认后再使用 --confirm-write 写入当前 profile。")
    return result


def setup_command(args) -> dict:
    home = Path(args.home) if args.home else default_home()
    home.mkdir(parents=True, exist_ok=True)
    plan = setup_plan(argparse.Namespace(home=str(home), json=None, python=getattr(args, "python", None), scan_root=[], model_tier=args.model_tier, quiet=True))
    missing = plan.get("missing") or []
    if not missing:
        result = {
            "stage": "setup_skipped",
            "home": str(home),
            "model_tier": args.model_tier,
            "status": "already_ready",
            "message": "当前环境已满足要求，无需重复安装或下载。",
            "plan": plan,
        }
        write_current_state(home, result)
        print("当前环境已满足要求，无需重复安装或下载。")
        env_python = (plan.get("qwen_local") or {}).get("env_python")
        if env_python:
            print(f"运行环境：{env_python}")
        print(f"模型目录：{(plan.get('paths') or {}).get('models_dir') or _default_models_dir(home)}")

        print("下一步建议提供 30-60 秒样片，运行 smoke-test。")
        return result

    unsupported_missing = [item for item in missing if item.get("type") not in {"python_env", "cuda_torch", "model"}]
    if unsupported_missing:
        result = {
            "stage": "setup_blocked",
            "home": str(home),
            "model_tier": args.model_tier,
            "status": "blocked_missing_external_dependency",
            "missing": unsupported_missing,
            "plan": plan,
        }
        write_current_state(home, result)
        print("setup 无法自动补齐以下外部依赖，请先安装/配置后再重试：")
        for item in unsupported_missing:
            print(f"- {item.get('label')}: {item.get('detail')}")
        return result

    env_missing = any(item.get("type") == "python_env" for item in missing)
    cuda_torch_missing = any(item.get("type") == "cuda_torch" for item in missing)
    if env_missing:
        print("检测到缺少 Qwen Python 运行环境。")
        print("我会在 runtime home 下创建独立环境，不修改系统 Python。")
        py = _create_or_update_qwen_env(home)
    else:
        py = _select_qwen_python(home=home, extra_python=getattr(args, "python", None))
        if cuda_torch_missing:
            print("检测到当前 Qwen Python 环境未启用 CUDA，正在安装 / 修复 CUDA 版 PyTorch。")
            _install_cuda_torch(py)
    models_dir = _default_models_dir(home)
    model_ids = [item["model_id"] for item in missing if item.get("type") == "model"]
    _download_missing_models(py, models_dir, model_ids)
    installed_or_downloaded = (["python_env"] if env_missing else []) + (["cuda_torch"] if cuda_torch_missing else []) + model_ids
    result = {"stage": "setup_completed", "home": str(home), "python": py, "models_dir": str(models_dir), "model_tier": args.model_tier, "installed_or_downloaded": installed_or_downloaded, "status": "ready"}
    write_current_state(home, result)
    print("缺失项已补齐。")
    print(f"运行环境：{py}")
    print(f"模型目录：{models_dir}")
    print("下一步建议提供 30-60 秒样片，运行 smoke-test。")
    return result


def smoke_test(args) -> dict:
    home = Path(args.home) if args.home else default_home()
    input_path = Path(args.input)
    sample_dir = home / "smoke-tests" / time.strftime("%Y%m%d-%H%M%S")
    sample_dir.mkdir(parents=True, exist_ok=True)
    sample_path = _extract_smoke_sample(input_path, sample_dir / f"{input_path.stem}_60s{input_path.suffix}", seconds=60, home=home)
    output_dir = sample_dir / "output"
    duration, duration_warnings = _probe_audio_duration_seconds(sample_path, home=home)
    started = time.perf_counter()
    ok = True
    error = None
    try:
        py = _select_qwen_python(home=home, extra_python=getattr(args, "python", None))
        cfg = _runner_config(input_path=sample_path, output_dir=output_dir, profile=args.profile, home=home, model_tier=args.model_tier, prefer_cuda=not getattr(args, "cpu", False))
        _call_qwen_runner(cfg, work_dir=sample_dir / "work", models_dir=_default_models_dir(home), python_executable=py, numba_cache_dir=home / "numba_cache")
    except Exception as e:
        ok = False
        error = repr(e)
    elapsed = time.perf_counter() - started
    runner_report_path = output_dir / "debug" / "run_report.json"
    runner_report = None
    if runner_report_path.exists():
        try:
            runner_report = json.loads(runner_report_path.read_text(encoding="utf-8-sig"))
        except Exception as e:
            runner_report = {"read_error": repr(e), "path": str(runner_report_path)}
    runner_system = (runner_report or {}).get("system") or {}
    duration_available = bool(duration and duration > 0)
    rtf = round(elapsed / duration, 3) if duration_available else None
    recommendation = _smoke_recommendation(ok, duration, elapsed, args.model_tier, error)
    warnings = list(duration_warnings)
    if ok and not duration_available:
        warnings.append("Subtitle generation succeeded, but sample_duration/rtf are unavailable because duration probing failed. ffprobe is recommended but not required.")
    if ok and not getattr(args, "cpu", False) and runner_system.get("cuda_available") is False:
        warnings.append("CUDA was requested by default, but the selected Python reports cuda_available=false; smoke-test ran on CPU.")
    result = {
        "stage": "smoke_test_completed",
        "success": ok,
        "profile": args.profile,
        "model_tier": args.model_tier,
        "input": str(input_path),
        "sample_path": str(sample_path),
        "output_dir": str(output_dir),
        "sample_duration": duration,
        "duration_available": duration_available,
        "processing_time": round(elapsed, 2),
        "rtf": rtf,
        "rtf_available": rtf is not None,
        "python": py if 'py' in locals() else None,
        "run_report": str(runner_report_path) if runner_report_path.exists() else None,
        "execution_path": {
            "cuda_requested": not getattr(args, "cpu", False),
            "cuda_available": runner_system.get("cuda_available"),
            "cuda_device": runner_system.get("cuda_device"),
            "device_used": runner_system.get("device_used"),
            "dtype": runner_system.get("dtype"),
            "torch": runner_system.get("torch"),
        },
        "recommendation": recommendation,
        "warnings": warnings,
        "error": error,
    }
    write_current_state(home, result)
    report_path = sample_dir / "smoke_report.json"
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if ok:
        print("运行测试完成。")
        print(f"耗时：{round(elapsed, 2)} 秒；RTF：{rtf if rtf is not None else '不可用'}")
        execution_path = result.get("execution_path") or {}
        print(f"执行路径：device_used={execution_path.get('device_used') or 'unknown'}；cuda_available={execution_path.get('cuda_available')}；cuda_device={execution_path.get('cuda_device') or 'none'}")
        if warnings:
            print("提示：")
            for item in warnings:
                print(f"- {item}")
        if recommendation == "install_or_enable_small":
            print("可以跑，但比较慢。建议批量视频先试小模型 small。")
        elif recommendation == "use_stronger_machine":
            print("可以跑，但当前机器比较慢。正式批量处理前，建议先用 30-60 秒真实样片再测一次；长视频可能耗时较久。")
        else:
            print("建议：可以进入正式 run 阶段。")
    else:
        print("运行测试失败。")
        print(error)
    print(f"测试报告：{report_path}")
    return result


def add_detection_args(p):
    p.add_argument("--home")
    p.add_argument("--json")
    p.add_argument("--python", help="Explicit Python executable to probe")
    p.add_argument("--scan-root", action="append", default=[], help="Optional bounded scan root for existing venvs; not used by default")


def add_qwen_runtime_args(p):
    p.add_argument("--home")
    p.add_argument("--backend", default="qwen-local", choices=["qwen-local"], help="Product backend is fixed to qwen-local")
    p.add_argument("--model-tier", default="best", choices=["best", "small"], help="best=Qwen3-ASR-1.7B, small=Qwen3-ASR-0.6B")
    p.add_argument("--python", help="Explicit Python executable with qwen_asr installed")
    p.add_argument("--cpu", action="store_true", help="Force CPU even when CUDA is available")


def main():
    ap = argparse.ArgumentParser(prog="lzp-video-subtitle")
    sub = ap.add_subparsers(dest="cmd", required=True)
    add_detection_args(sub.add_parser("healthcheck"))
    sp = sub.add_parser("setup-plan")
    add_detection_args(sp)
    sp.add_argument("--model-tier", default="best", choices=["best", "small"], help="Plan for best=Qwen3-ASR-1.7B or small=Qwen3-ASR-0.6B")
    p = sub.add_parser("init-profile")
    p.add_argument("--profile", required=True, help="Teacher/course/project profile name")
    p.add_argument("--home")
    p = sub.add_parser("setup")
    add_qwen_runtime_args(p)
    p = sub.add_parser("smoke-test")
    add_qwen_runtime_args(p)
    p.add_argument("--profile", default="general")
    p.add_argument("--input", required=True)
    p = sub.add_parser("run")
    p.add_argument("--input", required=True)
    p.add_argument("--output-dir")
    p.add_argument("--profile", default="general")
    p.add_argument("--model-tier", default="small", choices=["best", "small"])
    p.add_argument("--home")
    p.add_argument("--python", help="Explicit Python executable with qwen_asr installed")
    p.add_argument("--cpu", action="store_true", help="Force CPU even when CUDA is available")
    p = sub.add_parser("batch")
    p.add_argument("--input-dir", required=True)
    p.add_argument("--output-dir", help="Deprecated for default flow; batch defaults to one output folder next to each input video")
    p.add_argument("--profile", default="general")
    p.add_argument("--model-tier", default="small", choices=["best", "small"])
    p.add_argument("--home")
    p.add_argument("--python", help="Explicit Python executable with qwen_asr installed")
    p.add_argument("--cpu", action="store_true", help="Force CPU even when CUDA is available")
    p = sub.add_parser("learn")
    p.add_argument("--profile", default="general")
    p.add_argument("--raw", required=True, help="Original generated subtitle/text, e.g. final.srt")
    p.add_argument("--edited", required=True, help="Human-corrected subtitle/text")
    p.add_argument("--home")
    p.add_argument("--candidates-out", help="Optional review CSV path; default can be next to edited file")
    p.add_argument("--confirm-write", action="store_true", help="After human confirmation, append candidates into profile corrections.csv with backup")
    args = ap.parse_args()
    if args.cmd == "healthcheck":
        healthcheck(args)
    elif args.cmd == "setup-plan":
        setup_plan(args)
    elif args.cmd == "init-profile":
        init_profile(args)
    elif args.cmd == "run":
        run_command(args)
    elif args.cmd == "batch":
        batch_command(args)
    elif args.cmd == "learn":
        learn_command(args)
    elif args.cmd == "setup":
        setup_command(args)
    elif args.cmd == "smoke-test":
        smoke_test(args)


if __name__ == "__main__":
    main()
