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
from tqdm import tqdm

import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
import platform


from start_service import start_services, kill_service_on_port
from sandbox import create_docker_compose_file, start_docker_containers, stop_docker_containers, free_docker_port
from eval_db import eval_db

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from utils import dump_database, to_jsonable, DBWatcher
from agents import (
    InfoGatheringAgent,
    InfoGatheringAgentConfig,
    BackendTestingAgent,
    BackendTestingAgentConfig
)

DB_PORT = 5432
DB_CONFIG = dict(
    db_host="localhost",
    db_port=DB_PORT,
    db_username="myappuser",
    db_password="myapppassword",
    db_name="myapp",
)
MODEL_ID = os.environ["LLM_MODEL"]
MAX_INFO_GATHERING_RETRIES = 5

def load_json(in_file):
    with open(in_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def save_json(data, out_file):
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f)


def load_jsonl(in_file):
    datas = []
    with open(in_file, "r", encoding="utf-8") as f:
        for line in tqdm(f):
            datas.append(json.loads(line))
    return datas


def save_jsonl(datas, out_file, mode="w"):
    with open(out_file, mode, encoding="utf-8") as f:
        for data in tqdm(datas):
            f.write(json.dumps(data, ensure_ascii=False) + "\n")


def get_shell_start(app_paths, output_root):
    commands = {}
    for app_path in tqdm(app_paths):
        commands[os.path.basename(app_path)] = {"shell_actions": ["npm run install:all"], "last_start_action": "npm run dev"}

    save_json(commands, os.path.join(output_root, "commands.json"))
    return commands


def copy_db(orig_db_dir: str, db_tmp: str):
    if os.path.exists(db_tmp):
        shutil.rmtree(db_tmp)

    if not os.path.exists(orig_db_dir):
        os.makedirs(db_tmp, exist_ok=True)
        return

    if platform.system() != "Windows":
        try:
            subprocess.run(
                ["cp", "-a", "--reflink=auto", orig_db_dir, db_tmp],
                check=True
            )
            return
        except subprocess.CalledProcessError:
            pass          # fall through to Python copy on failure

    # Windows, or Unix reflink failed
    shutil.copytree(orig_db_dir, db_tmp)


def _run_single_gathering_agent(sample_id, working_dir, log_dir, model_id):
    if os.path.isfile(os.path.join(log_dir, "info_result.json")):
        return sample_id
    agent_config = InfoGatheringAgentConfig(
        model=model_id,
        working_dir=working_dir,
        log_dir=log_dir,
        max_history_length=100,
        max_iterations=100,
        overwrite=False,
        max_tokens=8192,
        compression_ratio=0.6,
    )
    agent = InfoGatheringAgent(agent_config)
    agent.run()
    return sample_id


def _info_worker_wrapper(arg_tuple):
    return _run_single_gathering_agent(*arg_tuple)


def _is_valid_info(info_file):
    if not os.path.isfile(info_file):
        return False
    try:
        with open(info_file, "r", encoding="utf-8") as f:
            info = json.load(f)
        if info is not None:
            return True
    except:
        return False
    return False


def run_info_gathering_agents(
    working_dir_root: str,
    log_dir_root: str,
    test_datas: list,
    model_id: str = MODEL_ID,
    max_workers: int | None = 32,
):
    # ---- book-keeping -----------------------------------------
    info_log = os.path.join(log_dir_root, "info_log.jsonl")
    done = set()
    if os.path.isfile(info_log):
        done = {d["id"] for d in load_jsonl(info_log) if _is_valid_info(os.path.join(log_dir_root, "info_gathering", d["id"], "info_result.json"))}
    pending = [d for d in test_datas if d["id"] not in done]
    if not pending:
        print("Nothing left to do.")
        return

    # ---- build the argument tuples ----------------------------------------
    task_args = []
    for d in pending:
        sid = d["id"]
        wdir = os.path.join(working_dir_root, sid)
        ldir = os.path.join(log_dir_root, "info_gathering", sid)
        task_args.append((sid, wdir, ldir, model_id))

    # ---- create the pool ---------------------------------------------------
    if max_workers is None:
        max_workers = mp.cpu_count()

    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        for sid in tqdm(
            pool.map(_info_worker_wrapper, task_args),
            total=len(task_args),
            desc="Info-gathering",
        ):
            # parent process only: append to the shared JSONL
            with open(info_log, "a", encoding="utf-8") as f:
                f.write(json.dumps({"id": sid}, ensure_ascii=False) + "\n")


def _run_single_testing_agent(sample_id, task, expected_result, working_dir, log_dir, model_id, info_path, db_dir, db_exists):
    if os.path.isfile(os.path.join(log_dir, "db_interaction_result.json")):
        return sample_id
    agent_config = BackendTestingAgentConfig(
        task=task,
        expected_result=expected_result,
        info_path=info_path,
        model=model_id,
        working_dir=working_dir,
        log_dir=log_dir,
        db_dir=db_dir,
        max_history_length=100,
        max_iterations=100,
        overwrite=True,
        max_tokens=8192,
        compression_ratio=0.6,
        db_exists=db_exists,
    )

    agent = BackendTestingAgent(agent_config)
    agent.run()
    return sample_id


def _testing_worker_wrapper(arg_tuple):
    return _run_single_testing_agent(*arg_tuple)


def run_backend_testing_agents(
    working_dir_root: str,
    log_dir_root: str,
    test_data: list,
    db_tmp: str,
    model_id: str = MODEL_ID,
    max_workers: int | None = 32,
    db_exists: bool = True,
):
    # ---- book-keeping (unchanged) -----------------------------------------
    testing_log = os.path.join(log_dir_root, "testing_log.jsonl")
    done = set()
    if os.path.isfile(testing_log):
        done = {d["task_id"] for d in load_jsonl(testing_log)}
    task_datas = test_data["backend_test_cases"]
    for task_idx, data in enumerate(task_datas):
        data["task_id"] = f"{test_data['id']}_{task_idx}"
    pending = [d for d in task_datas if d["task_id"] not in done]
    if not pending:
        print("Nothing left to do.")
        return

    info_path = os.path.join(log_dir_root, "info_gathering", test_data['id'], "info_result.json")
    wdir = os.path.join(working_dir_root, test_data['id'])

    # ---- build the argument tuples ----------------------------------------
    task_args = []
    for d in pending:
        sid = d["task_id"]
        task = d["instruction"]
        expected_result = d["expected_result"]
        ldir = os.path.join(log_dir_root, "results_backend", d["task_id"])
        task_args.append((sid, task, expected_result, wdir, ldir, model_id, info_path, db_tmp, db_exists))

    # ---- create the pool ---------------------------------------------------
    if max_workers is None:
        max_workers = mp.cpu_count()

    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        for sid in tqdm(
            pool.map(_testing_worker_wrapper, task_args),
            total=len(task_args),
            desc="Backend Testing",
        ):
            # parent process only: append to the shared JSONL
            with open(testing_log, "a", encoding="utf-8") as f:
                f.write(json.dumps({"task_id": sid}, ensure_ascii=False) + "\n")


def get_test_data(test_datas, sid):
    for d in test_datas:
        if d["id"] == sid:
            return d
    return None


def main():
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument("--in_dir", type=str)
    parser.add_argument("--log_dir", type=str)
    args = parser.parse_args()
    test_file = "data/WebGen-Bench_test-db-backend.json"
    test_datas = load_json(test_file)
    app_paths = [os.path.join(args.in_dir, data["id"]) for data in test_datas]

    output_root = args.log_dir
    log_file = os.path.join(output_root, "backend_log.jsonl")
    log_datas = []
    if os.path.isfile(log_file):
        log_datas = load_jsonl(log_file)

    processed_app_paths = [data["app_path"] for data in log_datas]
    filtered_app_paths = []
    for app_path in tqdm(app_paths):
        if app_path not in processed_app_paths:
            filtered_app_paths.append(app_path)
    app_paths = filtered_app_paths

    ## Info gathering
    for i in range(MAX_INFO_GATHERING_RETRIES):
        run_info_gathering_agents(args.in_dir, args.log_dir, test_datas)

    batch_size = 1
    backend_docker_compose_path = os.path.join(args.log_dir, "backend_docker")
    os.makedirs(backend_docker_compose_path, exist_ok=True)
    compose_path = os.path.join(backend_docker_compose_path, "docker-compose.yml")
    for i in range(0, len(app_paths), batch_size):
        batch_app_paths = app_paths[i:i + batch_size]
        working_dir = batch_app_paths[0]
        log_dir = os.path.join(args.log_dir, os.path.basename(working_dir))

        orig_db_dir = os.path.join(log_dir, "db")
        db_tmp = os.path.join(log_dir, "db_tmp")

        copy_db(orig_db_dir, db_tmp)
        db_watcher = DBWatcher(db_tmp)

        kill_service_on_port(DB_PORT)
        create_docker_compose_file(working_dir, log_dir, compose_path, db_tmp, db_port=DB_PORT)
        stop_docker_containers(compose_path)
        free_docker_port(DB_PORT)
        start_docker_containers(compose_path)
        commands = get_shell_start(batch_app_paths, args.in_dir)
        ports = start_services(args.in_dir, commands)
        print(ports)

        db_watcher.set_ckpt()
        ## Backend Testing
        sleep(30)
        test_data = get_test_data(test_datas, os.path.basename(working_dir))
        run_backend_testing_agents(args.in_dir, args.log_dir, test_data, db_tmp)
        new_entries = db_watcher.get_new_entries()
        print("============ New Entries ===========")
        print(new_entries)
        subprocess.run("pm2 delete all", shell=True)
        # shutil.rmtree(db_tmp, ignore_errors=True)
        
        curr_log_datas = [{"app_path": app_path} for app_path in batch_app_paths]
        save_jsonl(curr_log_datas, log_file, mode="a")


if __name__ == "__main__":
    main()