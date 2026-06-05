# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def safe_name(s: str) -> str:
    bad = '<>:"/\\|?*'
    out = ''.join('_' if ch in bad else ch for ch in s).strip()
    return out or 'sample'


def main():
    root = Path(__file__).resolve().parent.parent
    cfg_path = root / 'config_batch_3samples.json'
    cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
    samples = cfg.get('samples') or []
    if not samples:
        raise SystemExit('config_batch_3samples.json 里没有 samples')

    stamp = time.strftime('%Y%m%d_%H%M%S')
    batch_root = root / 'results_batch_3samples' / stamp
    batch_root.mkdir(parents=True, exist_ok=True)
    latest_file = root / 'results_batch_3samples' / 'LATEST.txt'
    latest_file.parent.mkdir(exist_ok=True)
    latest_file.write_text(str(batch_root), encoding='utf-8')
    summary = []
    t0 = time.time()

    for i, sample in enumerate(samples, 1):
        name = safe_name(sample.get('name') or f'sample_{i}')
        video = sample.get('video_path')
        out_dir = batch_root / name
        out_dir.mkdir(parents=True, exist_ok=True)
        one_cfg = dict(cfg)
        one_cfg.pop('samples', None)
        one_cfg['video_path'] = video
        one_cfg['output_dir'] = str(out_dir)
        one_cfg_path = out_dir / 'config.effective.json'
        one_cfg_path.write_text(json.dumps(one_cfg, ensure_ascii=False, indent=2), encoding='utf-8')
        log_path = out_dir / 'run.log'
        report_path = out_dir / 'run_report.json'
        final_srt_path = out_dir / 'final.srt'
        review_focus_path = out_dir / 'review_focus.csv'
        st = time.time()
        print(f'[{i}/{len(samples)}] RUN {name}: {video}', flush=True)
        try:
            env = os.environ.copy()
            env['QWEN_SUBTITLE_MODELS'] = r'D:\WorkBuddy_Local\qwen_local_3060_pilot\models'
            env['QWEN_SUBTITLE_WORK'] = r'D:\WorkBuddy_Local\qwen_subtitle_v5_work'
            with log_path.open('w', encoding='utf-8') as log:
                proc = subprocess.run([sys.executable, str(root / 'scripts' / 'qwen_local_gpu_v5.py'), '--config', str(one_cfg_path)], cwd=str(root), stdout=log, stderr=subprocess.STDOUT, text=True, env=env)
            ok = proc.returncode == 0
            report_path = out_dir / 'run_report.json'
            report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {}
            summary.append({
                'name': name,
                'video_path': video,
                'ok': ok,
                'returncode': proc.returncode,
                'elapsed_sec': round(time.time() - st, 2),
                'output_dir': str(out_dir),
                'final_srt': str(out_dir / 'final.srt'),
                'review_focus': str(out_dir / 'review_focus.csv'),
                'final_cues': (report.get('counts') or {}).get('final_cues'),
                'review_rows': (report.get('counts') or {}).get('review_rows'),
                'asr_sec': report.get('asr_sec'),
                'align_sec': report.get('align_sec'),
            })
        except Exception as e:
            summary.append({'name': name, 'video_path': video, 'ok': False, 'error': repr(e), 'elapsed_sec': round(time.time() - st, 2), 'output_dir': str(out_dir)})
        (batch_root / 'batch_summary.json').write_text(json.dumps({'elapsed_sec': round(time.time()-t0, 2), 'samples': summary}, ensure_ascii=False, indent=2), encoding='utf-8')

    md = ['# Qwen local GPU v5 batch summary', '', f'- batch_dir: `{batch_root}`', f'- elapsed_sec: {round(time.time()-t0, 2)}', '']
    for row in summary:
        md += [f"## {row.get('name')}", f"- ok: {row.get('ok')}", f"- elapsed_sec: {row.get('elapsed_sec')}", f"- final_cues: {row.get('final_cues')}", f"- review_rows: {row.get('review_rows')}", f"- output_dir: `{row.get('output_dir')}`", '']
    (batch_root / 'README.md').write_text('\n'.join(md), encoding='utf-8-sig')
    print(json.dumps({'elapsed_sec': round(time.time()-t0, 2), 'samples': summary}, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
