#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parallel screenshot gathering & de-duplication.

The heavy lifting still happens inside `gather_screenshots_single_task()`,
but the top-level loop is executed concurrently on all available CPU
cores (or a user-defined number of workers).
"""
import concurrent.futures as cf
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
from PIL import Image
from tqdm import tqdm


# --------------------------------------------------------------------------- #
# Utility                                                                     #
# --------------------------------------------------------------------------- #
def load_json(in_file: str):
    with open(in_file, "r", encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
# Distance                                                                    #
# --------------------------------------------------------------------------- #
def _image_distance_rgb(
    img_path_a: str,
    img_path_b: str,
    downscale: tuple[int, int] = (64, 64),
) -> float:
    """Mean absolute RGB difference on small thumbnails."""
    with Image.open(img_path_a) as a, Image.open(img_path_b) as b:
        a = a.convert("RGB").resize(downscale, Image.BILINEAR)
        b = b.convert("RGB").resize(downscale, Image.BILINEAR)

        arr_a = np.asarray(a, dtype=np.int16)
        arr_b = np.asarray(b, dtype=np.int16)

    return float(np.abs(arr_a - arr_b).sum(axis=-1).mean())


# --------------------------------------------------------------------------- #
# Core                                                                        #
# --------------------------------------------------------------------------- #
def gather_screenshots_single_task(
    test_logs_dir: str,
    sample_id: int | str,
    output_dir: str,
    image_threshold: float = 15.0,
    downscale: tuple[int, int] = (64, 64),
) -> list[str]:
    """Copy unique screenshots for one task to  {output_dir}/{sample_id}/shots/."""
    task_dirs = [
        os.path.join(test_logs_dir, d)
        for d in os.listdir(test_logs_dir)
        if d.startswith(f"task{sample_id}") and os.path.isdir(os.path.join(test_logs_dir, d))
    ]

    screenshots: list[str] = []
    for d in task_dirs:
        screenshots.extend(
            os.path.join(d, f)
            for f in os.listdir(d)
            if f.lower().endswith(".png")
        )

    if not screenshots:
        return []

    screenshots.sort()

    # ---- exact duplicates (hash) ----------------------------------------- #
    md5_seen: set[str] = set()
    uniq_after_hash: list[str] = []
    for path in screenshots:
        with open(path, "rb") as fh:
            md5 = hashlib.md5(fh.read()).hexdigest()
        if md5 not in md5_seen:
            md5_seen.add(md5)
            uniq_after_hash.append(path)

    # ---- near duplicates (distance) -------------------------------------- #
    accepted: list[str] = []
    thumbs: dict[str, np.ndarray] = {}

    def thumb(p: str) -> np.ndarray:
        if p not in thumbs:
            with Image.open(p) as img:
                img = img.convert("RGB").resize(downscale, Image.BILINEAR)
                thumbs[p] = np.asarray(img, dtype=np.int16)
        return thumbs[p]

    for cand in uniq_after_hash:
        dup = False
        cand_arr = thumb(cand)
        for acc in accepted:
            if np.abs(cand_arr - thumb(acc)).sum(axis=-1).mean() < image_threshold:
                dup = True
                break
        if not dup:
            accepted.append(cand)

    # ---- copy to output --------------------------------------------------- #
    shots_dir = Path(output_dir) / str(sample_id) / "shots"
    shots_dir.mkdir(parents=True, exist_ok=True)

    final_paths: list[str] = []
    for i, src in enumerate(accepted, 1):
        dst = shots_dir / f"shot_{i:05d}.png"
        shutil.copy2(src, dst)
        final_paths.append(str(dst))

    return final_paths


# --------------------------------------------------------------------------- #
# Parallel Orchestrator                                                       #
# --------------------------------------------------------------------------- #
def run_screenshot_gathering_parallel(
    samples: Sequence[int | str],
    test_logs_dir: Path | str,
    output_dir: Path | str,
    *,
    image_threshold: float = 15.0,
    downscale: tuple[int, int] = (64, 64),
    max_workers: int | None = None,
) -> None:
    """Execute one gather job per sample_id in parallel."""
    sample_ids = [d["id"] for d in samples]
    test_logs_dir = str(test_logs_dir)
    output_dir = str(output_dir)

    # Ensure output root exists before spawning processes (race-free).
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Default: use all CPUs.
    max_workers = max_workers or os.cpu_count() or 1

    with cf.ProcessPoolExecutor(max_workers=max_workers) as exe:
        futures = {
            exe.submit(
                gather_screenshots_single_task,
                test_logs_dir,
                sid,
                output_dir,
                image_threshold,
                downscale,
            ): sid
            for sid in sample_ids
        }

        for fut in tqdm(cf.as_completed(futures), total=len(futures), desc="gathering screenshots"):
            sid = futures[fut]
            try:
                fut.result()
            except Exception as e:
                # Keep going even if one task fails.
                print(f"[!] sample {sid!r} failed: {e}", file=sys.stderr)


# --------------------------------------------------------------------------- #
# CLI                                                                        #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    root_dir = "/mnt/cache/k12_data/WebGen-Agent2/logs_root/model-Qwen3-Coder-30B-A3B-Instruct_hist-100_iter-400_compress-0.5_val-1_sum-5_v8"
    test_logs_dir = Path(root_dir) / "results"
    output_dir = Path(root_dir) / "results_appearance"

    test_file = "/mnt/cache/agent/Zimu/WebGen-Bench/data/WebGen-Bench_test-db-backend.json"
    samples = load_json(test_file)

    # ---- run in parallel -------------------------------------------------- #
    run_screenshot_gathering_parallel(
        samples,
        test_logs_dir,
        output_dir,
        image_threshold=15.0,
        downscale=(64, 64),
        max_workers=None,  # set to an int to limit concurrency
    )