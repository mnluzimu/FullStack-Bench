#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import zipfile
from tqdm import tqdm
import time
import re
from typing import List, Tuple
import json
import subprocess
from pathlib import Path
import sys
from time import sleep
import shutil
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback

from dotenv import load_dotenv
load_dotenv()

# Add the parent directory to sys.path to enable imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sandbox import create_docker_compose_file, start_docker_containers, stop_docker_containers, free_docker_port
from start_service import start_services, kill_service_on_port
from utils import dump_database, llm_generation, to_jsonable
from db_compute_acc import db_compute_acc

def load_json(in_file):
    with open(in_file, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data, out_file):
    Path(out_file).parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_jsonl(in_file):
    items = []
    with open(in_file, "r", encoding="utf-8") as f:
        for line in f:
            items.append(json.loads(line))
    return items


def save_jsonl(datas, out_file, mode="w"):
    Path(out_file).parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, mode, encoding="utf-8") as f:
        for data in datas:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")


def copy_db(orig_db_dir, db_tmp):
    """Fast clone of the db directory into a temp directory (reflink when possible)."""
    if os.path.exists(db_tmp):
        shutil.rmtree(db_tmp)
    if os.path.exists(orig_db_dir):
        try:
            subprocess.run(
                ["cp", "-a", "--reflink=auto", orig_db_dir, db_tmp],
                check=True,
            )
        except subprocess.CalledProcessError:
            shutil.copytree(orig_db_dir, db_tmp)
    else:
        os.makedirs(db_tmp, exist_ok=True)  # create empty dir

# ------------------------------------------------------------------ #
#           Robust JSON-block extractor from LLM responses            #
# ------------------------------------------------------------------ #

_JSON_FENCE_RE = re.compile(r"```(?:\s*json)?\s*(.*?)```", re.I | re.S)


def _find_brace_block(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def parse_grade_response(raw_text: str) -> dict:
    """Return dict with Q-keys or empty dict if parsing fails."""
    m = _JSON_FENCE_RE.search(raw_text)
    if m:
        candidate = m.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    brace_block = _find_brace_block(raw_text)
    if brace_block:
        try:
            return json.loads(brace_block)
        except json.JSONDecodeError:
            pass
    return {}

# ------------------------------------------------------------------ #
#                Prompt template for coverage grading                #
# ------------------------------------------------------------------ #

GRADE_PROMPT_TEMPLATE = """You are a meticulous software engineer specialised in databases.

Below is the implemented database schema (tables → columns with a few rows) dumped at runtime.

IMPLEMENTED DATABASE SCHEMA:
```json
{implemented_schema}
```

Answer the following question:
Does the database contain {required_content}?

Consider whether the implemented database contain a table (or a combination of tables) that can provide the content in the question.
Answer "Yes" if:
  - a single table matches, OR
  - several tables together cover the purpose, OR
  - a superset of a table matches.
Otherwise answer "No".

Steps for you:
1. Think step-by-step.  Show your reasoning for each question.
2. After finishing all reasoning, output ONLY one valid JSON object
   fenced in ```json … ``` with the key "answer".
   - If the answer is yes, output: {{"answer": "Yes"}}
   - Otherwise, output: {{"answer": "No"}}"""

def build_grade_prompt(required_content: str, implemented_dump: dict) -> str:
    return GRADE_PROMPT_TEMPLATE.format(
        required_content=required_content,
        implemented_schema=json.dumps(
            implemented_dump, indent=2, ensure_ascii=False
        ),
    )

# ------------------------------------------------------------------ #
#                 Paths and model configuration                       #
# ------------------------------------------------------------------ #

MODEL_ID = os.environ["LLM_MODEL"]
TEST_FILE = "/mnt/cache/agent/Zimu/WebGen-Bench/src/generate_fullstack_tests/WebGen-Bench_test-db-backend.json"

DB_CONFIG = dict(
    db_host="localhost",
    db_port=6434,
    db_username="myappuser",
    db_password="myapppassword",
    db_name="myapp",
)

# ------------------------------------------------------------------ #
#                   Utility path helpers                              #
# ------------------------------------------------------------------ #

def locate_dump(sample_id: str, log_dir) -> str:
    dump_dir = os.path.join(log_dir, sample_id)
    return os.path.join(dump_dir, "db_dump.json")


def locate_grade(sample_id: str, test_case_id: int, log_dir) -> str:
    dump_dir = os.path.join(log_dir, sample_id)
    return os.path.join(dump_dir, f"db_grade_{test_case_id}.json")

# ------------------------------------------------------------------ #
#                       Grading worker                                #
# ------------------------------------------------------------------ #

MAX_RETRIES = 10

def grade_sample(sample: dict, log_dir):
    sid = sample["id"]
    test_case_id = sample["test_case_id"]
    dump_path = locate_dump(sid, log_dir)
    grade_path = locate_grade(sid, test_case_id, log_dir)

    # If the db_dump.json is missing we cannot grade.
    if not os.path.isfile(dump_path):
        print(f"[WARN] missing dump for {sid}, skipping grading")
        return

    if os.path.isfile(grade_path):
        print(f"{grade_path} already exists")
        return

    implemented_dump = load_json(dump_path)
    required_content = sample["data_content"]

    prompt = build_grade_prompt(required_content, implemented_dump)

    answer = False
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"[INFO] grading {sid}, prompt length: {len(prompt)}")
            llm_resp = llm_generation([{"role": "user", "content": prompt}], model=MODEL_ID)
            coverage = parse_grade_response(llm_resp.get("content", ""))

            # count "Yes"
            answer = True if coverage["answer"].lower() == "yes" else False
            break
        except:
            pass

    result_blob = {
        "db_coverage_evaluation": coverage,
        "answer": answer,
        "prompt": prompt,
        "llm_response": llm_resp.get("content", ""),
    }
    print(f"[INFO] graded {sid}: saving to {grade_path}")
    save_json(result_blob, grade_path)

# ------------------------------------------------------------------ #
#                              main                                   #
# ------------------------------------------------------------------ #

def main():
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument("--in_dir", type=str, required=True,
                        help="Directory that contains generated applications (each in a sub-dir named by id)")
    parser.add_argument("--log_dir", type=str, required=True,
                        help="Directory to store docker logs, dumps, grades …")
    args = parser.parse_args()

    eval_db(args.in_dir, args.log_dir)


def eval_db(in_dir_root, log_dir_root):
    # ---------------- Load dataset ---------------------------------- #
    test_datas = load_json(TEST_FILE)
    app_dirs = {d["id"]: os.path.join(in_dir_root, d["id"]) for d in test_datas}

    # ---------------- Phase 1: boot app, dump DB -------------------- #
    print("=== Phase-1: start containers & dump database ===")
    for sample in tqdm(test_datas, desc="Dumping DB"):
        sid = sample["id"]
        working_dir = app_dirs[sid]
        log_dir = os.path.join(log_dir_root, sid)
        dump_path = locate_dump(sid, log_dir_root)
        print(dump_path)

        # Skip if dump already exists
        if os.path.isfile(dump_path):
            continue

        compose_dir = os.path.join(log_dir, f"docker_{sid}")
        compose_path = os.path.join(compose_dir, "docker-compose.yml")
        orig_db_dir = os.path.join(log_dir, "db")
        db_tmp = os.path.join(log_dir, "db_tmp")

        os.makedirs(compose_dir, exist_ok=True)
        copy_db(orig_db_dir, db_tmp)

        create_docker_compose_file(
            working_dir, log_dir, compose_path, db_tmp, db_port=DB_CONFIG["db_port"]
        )

        stop_docker_containers(compose_path)
        kill_service_on_port(DB_CONFIG["db_port"])
        free_docker_port(DB_CONFIG["db_port"])
        start_docker_containers(compose_path)

        sleep(10)  # wait for services

        try:
            dump = dump_database(DB_CONFIG, limit=5, connect_timeout=60)
            dump = to_jsonable(dump)
            save_json(dump, dump_path)
        except Exception as e:
            print(f"Dump database failed with error: {str(e)}")

        stop_docker_containers(compose_path)
        shutil.rmtree(db_tmp, ignore_errors=True)

    # ---------------- Phase 2: grading ------------------------------ #
    print("=== Phase-2: grade DB coverage ===")

    divided_samples = []
    for s in test_datas:
        divided_samples.extend([{"id": s["id"], "test_case_id": i, "data_content": d} for i, d in enumerate(s["data_structures"])])
    print(divided_samples)

    overwrite_grades = True
    if overwrite_grades:
        samples_to_grade = divided_samples
    else:
        # Filter samples that still need grading
        samples_to_grade = [
            s for s in divided_samples if not os.path.isfile(locate_grade(s["id"], s["test_case_id"], log_dir_root))
        ]

    max_workers = min(32, multiprocessing.cpu_count() * 2)
    with ThreadPoolExecutor(max_workers=max_workers) as exe:
        # ---------- submit all jobs -------------
        futures = {
            exe.submit(grade_sample, s, log_dir_root): s["id"]
            for s in samples_to_grade
        }

        # ---------- harvest results -------------
        for future in tqdm(as_completed(futures),
                           total=len(futures),
                           desc="Grading"):
            sid = futures[future]
            try:
                # if grade_sample raised, this will re-raise here
                future.result()
            except Exception as err:
                # show the error, *do not* swallow it
                print(f"\n[ERROR] grading sample {sid} failed: {err}")
                traceback.print_exc()
                raise

    print(f"[DONE] graded {len(samples_to_grade)} new samples.")
    db_compute_acc(os.path.join(log_dir_root))


if __name__ == "__main__":
    main()
    # sample = {"id": "000001", "test_case_id": 0, "data_content": "stock information"}
    # log_dir = "/mnt/cache/agent/Zimu/WebGen-Agent2/logs_root/model-qwen3_coder_30b_full_fullstack-agent_checkpoint-300_hist-100_iter-400_compress-0.5_val-1_sum-5_v8_pure-frontend-compatible5"
    # grade_sample(sample, log_dir)