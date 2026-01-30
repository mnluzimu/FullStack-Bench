import os
import json
from pathlib import Path
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor, as_completed

from get_screenshots import capture_scroll_screenshots
from vlm_eval import get_score_result
from gather_screenshots import run_screenshot_gathering_parallel
from compute_grade import get_grade
from dotenv import load_dotenv
load_dotenv()  # take environment variables from .env file

# ------------- utils (unchanged) -----------------
def load_json(in_file):
    with open(in_file, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data, out_file):
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def load_jsonl(in_file):
    datas = []
    with open(in_file, "r", encoding="utf-8") as f:
        for line in tqdm(f, desc="loading jsonl"):
            datas.append(json.loads(line))
    return datas
# -------------------------------------------------

def score_single(idx: int,
                 datum: dict,
                 output_root: str,
                 tag: str,
                 model: str,
                 thresh: int = 3) -> str:
    """
    Run `get_score_result` for a single app and persist the result.
    Returns a short status string for logging.
    """
    app = f"{idx + 1:06d}"
    shot_path = os.path.join(output_root, app, "shots")
    result_path = os.path.join(shot_path, f"result{tag}.json")

    # if os.path.isfile(result_path):
    #     return f"[{app}] result already exists – skipped"

    if not os.path.isdir(shot_path):
        return f"[{app}] no shots dir – skipped"

    image_paths = [os.path.join(shot_path, fn)
                   for fn in os.listdir(shot_path)
                   if fn.endswith(".png")][:thresh]
    print(image_paths)
    if not image_paths:
        return f"[{app}] no .png files – skipped"

    # ---- heavy work ---------------------------------------------------------
    output = get_score_result(image_paths,
                              datum["instruction"],
                              model=model)
    # -------------------------------------------------------------------------
    save_json({"model_output": output}, result_path)
    return f"[{app}] processed {len(image_paths)} images"


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("in_dir", type=str, help="folder that contains the zip archives")
    parser.add_argument("--tag",   type=str, default="",   help="suffix for result file names")
    parser.add_argument("--model", type=str, default="", help="VLM to call")
    parser.add_argument("--num-workers", type=int, default=os.cpu_count(),
                        help="parallel workers (default = #cores)")
    args = parser.parse_args()

    if args.model == "":
        args.model = os.getenv("VLM_MODEL")

    test_datas = load_jsonl("/mnt/cache/agent/Zimu/WebGen-Bench/data/WebGen-Bench_test-db-backend.jsonl")
    test_logs_dir = Path(args.in_dir) / "results"
    output_dir = Path(args.in_dir) / "results_appearance"

    run_screenshot_gathering_parallel(
        test_datas,
        test_logs_dir,
        output_dir,
        image_threshold=15.0,
        downscale=(64, 64),
        max_workers=args.num_workers,
    )

    tasks = [(idx, data, output_dir, args.tag, args.model)
             for idx, data in enumerate(test_datas)]

    with ProcessPoolExecutor(max_workers=args.num_workers) as pool:
        futures = [pool.submit(score_single, *t) for t in tasks]

        for fut in tqdm(as_completed(futures), total=len(futures), desc="scoring"):
            # `result()` re-raises exceptions from worker processes, so you
            # notice problems immediately instead of silently skipping.
            try:
                msg = fut.result()
                print(msg)
            except Exception as e:
                print(f"Worker raised an exception: {e}")

    print("✓ All apps processed.")

    grade = get_grade(output_dir, prefix="00", tag=args.tag)
    print(grade)


if __name__ == "__main__":
    main()