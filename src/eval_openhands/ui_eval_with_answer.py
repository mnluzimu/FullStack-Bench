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

from start_service import start_services, kill_service_on_port
from sandbox import create_docker_compose_file, start_docker_containers, stop_docker_containers, free_docker_port
from eval_db import eval_db
from compute_acc import compute_acc
from eval_backend import run_info_gathering_agents, get_test_data, run_backend_testing_agents
from webvoyager import run_single_task
from backend_compute_acc import backend_compute_acc

from initialize_db import initialize_db, find_first_sql

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import dump_database, to_jsonable, nuke_processes

from dotenv import load_dotenv
load_dotenv()

DB_PORT = 5432
DB_CONFIG = dict(
    db_host="localhost",
    db_port=DB_PORT,
    db_username="myappuser",
    db_password="myapppassword",
    db_name="myapp",
)

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


ui_prompt_template = """

Task: {task}

Expected Result: {expected_result}

Instructions:
- Attempt the task as a user would, using the UI elements available.
- Make multiple attempts if needed to try and achieve the expected result.
- Observe whether the expected result is fully, partially, or not at all achieved.
- IMPORTANT: You can at most interact with the website 15 times. If the limit is reached, directly output your answer.
- If prompted for a username, password, or email in the process of testing, enter "superadmin@example.com", "admin123", and "superadmin@example.com", respectively.
- If login is unsuccessful, try to register a new account first.

At the end of your testing, answer only with one of the following:
- YES: if the expected result was fully achieved.
- NO: if the expected result could not be achieved at all.
- PARTIAL: if only some aspects of the expected result were achieved.

"""


def create_tasks_test(test_file, ports, tasks_file):
    datas = load_json(test_file)
    tasks = []
    for idx, data in tqdm(enumerate(datas)):
        app = data["id"]
        if app not in ports.keys():
            continue
        for ui_idx, ui_instruct in enumerate(data["ui_instruct"]):
            instruction = ui_prompt_template.format(task=ui_instruct["task"], expected_result=ui_instruct["expected_result"])
            tasks.append({
                "web_name": data["id"],
                "id": f"{app}_{ui_idx}",
                "ques": instruction,
                "web": f"http://localhost:{ports[app]}/",
                "expected_result": ui_instruct["expected_result"],
                "task": ui_instruct["task"]
            })
    save_jsonl(tasks, tasks_file)


def run_webvoyager(input_dir, db_dir=None):
    from webvoyager.run_webvoyager import run_single_task
    import concurrent.futures
    import json
    from pathlib import Path

    input_dir = Path(input_dir)
    tasks_file = input_dir / "tasks_test_with_answer.jsonl"
    output_dir = input_dir / "results"
    download_dir = input_dir / "downloads"

    # Create output and download directories
    output_dir.mkdir(exist_ok=True)
    download_dir.mkdir(exist_ok=True)

    # Load tasks
    tasks = []
    with open(tasks_file, "r", encoding="utf-8") as f:
        for line in f:
            tasks.append(json.loads(line))

    # Define arguments for run_single_task
    args_dict = {
        "test_file": str(tasks_file),
        "max_iter": 15,
        "api_key": "sk-mah6FUel7jrB3lNj8c3cnqUGeKy1ovL5DAD1GFge92C7Fe864c8646B1B9DaB6C20a10A896",
        "api_model": os.environ["VLM_MODEL"],
        "output_dir": str(output_dir),
        "seed": 42,
        "max_attached_imgs": 3,
        "temperature": 1.0,
        "download_dir": str(download_dir),
        "text_only": False,
        "headless": True,
        "save_accessibility_tree": False,
        "force_device_scale": False,
        "window_width": 1600,
        "window_height": 1200,
        "fix_box_color": True,
        "num_workers": 8
    }

    # Run tasks in parallel using ProcessPoolExecutor as in the original
    with concurrent.futures.ProcessPoolExecutor(max_workers=args_dict["num_workers"]) as executor:
        futures = [executor.submit(run_single_task, task, args_dict, db_dir) for task in tasks]
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()  # This will raise an exception if the task failed
            except Exception as exc:
                print(f"Task generated an exception: {exc}")


def copy_db(orig_db_dir, db_tmp):
    if os.path.exists(db_tmp):
        shutil.rmtree(db_tmp)          # old leftovers
    if os.path.exists(orig_db_dir):
        # Copy as fast as possible: use reflink on capable filesystems,
        # fallback to regular copy otherwise.
        try:
            subprocess.run(
                ["cp", "-a", "--reflink=auto", orig_db_dir, db_tmp],
                check=True
            )
        except subprocess.CalledProcessError:
            shutil.copytree(orig_db_dir, db_tmp)
    else:
        os.makedirs(db_tmp, exist_ok=True)  # empty cluster


def make_html(in_dir):
    if not os.path.exists(os.path.join(in_dir, "frontend")):
        return
    html_path = os.path.join(in_dir, "frontend/public/index.html")
    html_content = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <link rel="icon" href="%PUBLIC_URL%/favicon.ico" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="theme-color" content="#000000" />
    <meta
      name="description"
      content="A Web Project"
    />
    <title>A Web Project</title>
  </head>
  <body style="background-color: ivory;">
    <noscript>You need to enable JavaScript to run this app.</noscript>
    <div id="root"></div>
  </body>
</html>"""
    if not os.path.exists(html_path):
        os.makedirs(os.path.dirname(html_path), exist_ok=True)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)


def make_index_js(in_dir):
    if not os.path.exists(os.path.join(in_dir, "frontend")):
        return
    index_js_content = """import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);"""
    index_css_content = """body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen',
    'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue',
    sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background-color: ivory;
}

code {
  font-family: source-code-pro, Menlo, Monaco, Consolas, 'Courier New',
    monospace;
}"""
    index_js_path = os.path.join(in_dir, "frontend/src/index.js")
    index_css_path = os.path.join(in_dir, "frontend/src/index.css")
    if not os.path.exists(index_css_path):
        os.makedirs(os.path.dirname(index_css_path), exist_ok=True)
        with open(index_css_path, "w", encoding="utf-8") as f:
            f.write(index_css_content)
    if not os.path.exists(index_js_path):
        os.makedirs(os.path.dirname(index_js_path), exist_ok=True)
        with open(index_js_path, "w", encoding="utf-8") as f:
            f.write(index_js_content)


def get_app_path(app_path):
    dir_content = [e for e in os.listdir(app_path) if e not in ["conversations", "db", 'start-wrapper.cjs']]
    print(f"\n\ndir_content: {dir_content}\n\n")
    if len(dir_content) == 1 and os.path.isdir(os.path.join(app_path, dir_content[0])):
        app_path = os.path.join(app_path, dir_content[0])
    return app_path



def main():
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument("--in_dir", type=str)
    parser.add_argument("--log_dir", type=str)
    args = parser.parse_args()
    in_dir = args.in_dir
    test_file = "/mnt/cache/agent/Zimu/WebGen-Bench/src/generate_fullstack_tests/WebGen-Bench_test-db-backend.json"
    test_datas = load_json(test_file)
    app_paths = [os.path.join(in_dir, data["id"]) for data in test_datas]

    output_root = args.log_dir
    tasks_file = os.path.join(output_root, "tasks_test_with_answer.jsonl")
    log_file = os.path.join(output_root, "log.jsonl")
    log_datas = []
    if os.path.isfile(log_file):
        log_datas = load_jsonl(log_file)

    processed_app_paths = [data["app_path"] for data in log_datas]

    filtered_app_paths = []
    for app_path in tqdm(app_paths):
        if app_path not in processed_app_paths:
            filtered_app_paths.append(app_path)
    app_paths = filtered_app_paths

    # gather info for backend testing
    run_info_gathering_agents(args.in_dir, args.log_dir, test_datas)

    batch_size = 1
    compose_path = os.path.join(args.log_dir, "docker-compose.yml")
    for i in range(0, len(app_paths), batch_size):
        nuke_processes(r"npm run dev")
        batch_app_paths = app_paths[i:i + batch_size]
        working_dir = batch_app_paths[0]
        log_dir = os.path.join(args.log_dir, os.path.basename(working_dir))

        orig_db_dir = os.path.join(working_dir, "db")
        db_tmp = os.path.join(log_dir, "db_tmp")

        copy_db(orig_db_dir, db_tmp)

        kill_service_on_port(DB_PORT)
        kill_service_on_port(5000)
        kill_service_on_port(3000)
        kill_service_on_port(3001)
        create_docker_compose_file(working_dir, log_dir, compose_path, db_tmp, db_port=DB_PORT)
        stop_docker_containers(compose_path)
        try:
            free_docker_port(DB_PORT)
        except Exception as e:
            print(f"Free docker port {DB_PORT} failed with error: {str(e)}")
        start_docker_containers(compose_path)

        sleep(30)

        app_path = get_app_path(working_dir)
        make_html(app_path)
        make_index_js(app_path)
        sql_file = find_first_sql(app_path)
        if sql_file is not None:
            print(f"\n\nfound sql file: {sql_file}\n\n")
            initialize_db(sql_file)

        commands = get_shell_start(batch_app_paths, args.in_dir)
        ports = start_services(args.in_dir, commands)
        print(ports)

        create_tasks_test(test_file, ports, tasks_file)
        sleep(30)

        # test backend
        test_data = get_test_data(test_datas, os.path.basename(working_dir))
        run_backend_testing_agents(args.in_dir, args.log_dir, test_data, db_tmp)

        # test frontend
        run_webvoyager(output_root, db_tmp)

        try:
            dump = dump_database(DB_CONFIG, limit=5, connect_timeout=60)
            dump = to_jsonable(dump)
            save_json(dump, os.path.join(log_dir, "db_dump.json"))
        except Exception as e:
            print(f"Dump database failed with error: {str(e)}")

        subprocess.run("pm2 delete all", shell=True)
        shutil.rmtree(db_tmp, ignore_errors=True)

        curr_log_datas = [{"app_path": app_path} for app_path in batch_app_paths]
        save_jsonl(curr_log_datas, log_file, mode="a")

    nuke_processes(r"npm run dev")
    kill_service_on_port(5000)
    kill_service_on_port(3000)
    kill_service_on_port(3001)
    compute_acc(args.log_dir)
    backend_compute_acc(args.log_dir)
    eval_db(args.in_dir, args.log_dir)


if __name__ == "__main__":
    main()
