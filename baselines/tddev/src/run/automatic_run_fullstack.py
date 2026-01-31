"""
automatic_run_fullstack.py

Drives the TDDev evaluation pipeline end-to-end.

NEW:
- The FastAPI client app is now started in the background for
  every sample and stopped afterwards.  A 60-second
  cool-down is enforced between samples to make sure no
  request from the previous run is still being processed.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List
import multiprocessing as _mp

from types import ModuleType
from typing import Any

from tqdm import tqdm
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from sandbox import (
    create_docker_compose_file,
    free_docker_port,
    start_docker_containers,
    stop_docker_containers,
)

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────
BOLT_DIY_ADDRESS = "http://localhost:5173/"
TDDEV_CLIENT_ADDRESS = "http://127.0.0.1:8003/"
CLIENT_APP_PY = os.path.abspath(r"client\app.py")

CHROME_BINARY = (
    r"C:\Users\luzim\AppData\Local\Google\Chrome SxS\Application\chrome.exe"
)

DOWNLOAD_PATH = os.path.abspath(r"downloads\qwen3coder30B")
OUTPUT_DIR = os.path.abspath(r"outputs\qwen3coder30B")
LAST_ZIP_LOG_PATH = os.path.abspath(r"client\last_zip_path_log.txt")
LOG_DIR = os.path.abspath(r"outputs\qwen3coder30B_logs")
WORKING_DIR = os.path.abspath(r"outputs\qwen3coder30B_workspace")

TIMEOUT_MIN = 50
WAIT_AFTER_STOP_SEC = 60
PORT_CHECK_TIMEOUT_SEC = 60

# Make sure mandatory directories exist
for _d in (DOWNLOAD_PATH, OUTPUT_DIR):
    os.makedirs(_d, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
#  Robust client-service life-cycle helpers
# ──────────────────────────────────────────────────────────────────────────────
CLIENT_DIR = Path(r"client").resolve()
CLIENT_HOST = "127.0.0.1"
CLIENT_PORT = 8003


# ─── generic import/load of client/app.py ─────────────────────────────────────
def _load_client_module() -> tuple[Any, str]:
    """
    Dynamically loads `client/app.py` (or another file – adjust path if needed)
    and returns the exported web-app instance plus a string describing its type
    ("fastapi" or "flask").
    """
    import importlib.util
    import sys

    module_path = (CLIENT_DIR / "app.py").resolve()
    if not module_path.exists():
        raise FileNotFoundError(f"entry file not found: {module_path}")

    sys.path.insert(0, str(CLIENT_DIR))  # so internal imports work

    spec = importlib.util.spec_from_file_location("client_app", module_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec.loader is not None
    spec.loader.exec_module(mod)                 # type: ignore[attr-defined]

    # Accept variable  'app' or 'application'
    web_app = getattr(mod, "app", None) or getattr(mod, "application", None)
    if web_app is None:
        raise RuntimeError(
            f"{module_path} must expose a variable called 'app' or 'application'"
        )

    cls_name = web_app.__class__.__name__.lower()
    if "fastapi" in cls_name:
        return web_app, "fastapi"
    if "flask" in cls_name:
        return web_app, "flask"

    raise RuntimeError(
        f"Unsupported web-framework class {web_app.__class__.__name__}; "
        "only FastAPI and Flask are handled automatically."
    )


# ─── launcher that supports both ASGI & WSGI apps ────────────────────────────
def _serve_in_subprocess() -> None:
    """
    Executed in a separate interpreter via multiprocessing.Process.
    Detects the framework and starts either uvicorn (FastAPI) or
    waitress (Flask).  Blocks until the process is terminated.
    """
    import os
    from pathlib import Path

    web_app, kind = _load_client_module()

    # ──────────────────────────────────────────────
    # Fix template / static lookup for Flask
    # ──────────────────────────────────────────────
    if kind == "flask":
        from flask import Flask

        if isinstance(web_app, Flask):
            # Ensure absolute, canonical paths
            client_dir = Path(CLIENT_DIR).resolve()

            web_app.root_path = str(client_dir)
            web_app.template_folder = str(client_dir / "templates")
            web_app.static_folder = str(client_dir / "static")
    # ──────────────────────────────────────────────

    os.chdir(CLIENT_DIR)  # keep relative paths in user code working

    if kind == "fastapi":
        import uvicorn

        uvicorn.run(
            web_app,
            host=CLIENT_HOST,
            port=CLIENT_PORT,
            log_level="info",
            workers=1,
            reload=False,
            access_log=False,
        )
    else:  # kind == "flask"
        from waitress import serve

        serve(
            web_app,
            host=CLIENT_HOST,
            port=CLIENT_PORT,
            threads=4,
            _quiet=True,
        )


def _start_client_app() -> _mp.Process:
    """
    Forks / spawns a daemon process that runs the client web-service.
    Returns the Process object.
    """
    proc = _mp.Process(target=_serve_in_subprocess, daemon=True)
    proc.start()
    return proc


def _stop_client_app(proc: _mp.Process, timeout: int = 10) -> None:
    """
    Attempts graceful termination; falls back to a hard kill.
    """
    if not proc.is_alive():
        return
    proc.terminate()
    proc.join(timeout)
    if proc.is_alive():
        proc.kill()
        proc.join()


# ─── port-readiness probe ────────────────────────────────────────────────────
def _is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        try:
            s.connect((host, port))
            return True
        except OSError:
            return False


def wait_until_client_ready(timeout_sec: int = 60) -> None:
    """
    Block until TCP <host>:<port> is reachable or raise TimeoutError.
    """
    elapsed = 0
    while elapsed < timeout_sec:
        if _is_port_open(CLIENT_HOST, CLIENT_PORT):
            return
        time.sleep(1)
        elapsed += 1
    raise TimeoutError(f"client service did not open {CLIENT_PORT} within {timeout_sec}s")


# ──────────────────────────────────────────────────────────────────────────────
# Browser helpers (unchanged except for minor formatting)
# ──────────────────────────────────────────────────────────────────────────────
def _new_driver(download_path: str, chrome_binary: str | None = None) -> webdriver.Chrome:
    download_path = str(Path(download_path).expanduser().resolve())
    os.makedirs(download_path, exist_ok=True)

    opts = ChromeOptions()
    opts.add_argument("--start-maximized")
    if chrome_binary:
        if not Path(chrome_binary).exists():
            raise FileNotFoundError(f"Chrome binary not found: {chrome_binary}")
        opts.binary_location = chrome_binary

    prefs: Dict[str, object] = {
        "download.default_directory": download_path,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "profile.default_content_setting_values.automatic_downloads": 1,
    }
    opts.add_experimental_option("prefs", prefs)
    opts.add_argument("--disable-popup-blocking")

    service = ChromeService()
    return webdriver.Chrome(service=service, options=opts)


def _open_two_windows(driver: webdriver.Chrome) -> List[str]:
    driver.get(BOLT_DIY_ADDRESS)
    first_handle = driver.current_window_handle

    driver.switch_to.new_window("window")
    driver.get(TDDEV_CLIENT_ADDRESS)
    second_handle = driver.current_window_handle

    return [first_handle, second_handle]


# ──────────────────────────────────────────────────────────────────────────────
# Core: one UI interaction
# ──────────────────────────────────────────────────────────────────────────────
def run_single_instruction(
    instruction: str,
    test_id: str = "",
    download_path: str = "./downloads",
    output_dir: str = "./outputs",
    chrome_binary: str | None = CHROME_BINARY,
) -> None:
    driver = _new_driver(download_path, chrome_binary)
    win0, win1 = _open_two_windows(driver)

    try:
        driver.switch_to.window(win1)
        wait = WebDriverWait(driver, 30)

        # Clear cache if possible
        try:
            clear_btn = wait.until(
                EC.presence_of_element_located((By.ID, "clear-cache-btn"))
            )
            if clear_btn.is_displayed() and clear_btn.is_enabled():
                clear_btn.click()
                wait.until(EC.staleness_of(clear_btn))
                wait.until(EC.presence_of_element_located((By.ID, "prompt")))
        except Exception:
            pass  # button may be absent

        # Select model if dropdown is enabled
        try:
            model_sel = wait.until(EC.presence_of_element_located((By.ID, "model")))
            if model_sel.is_enabled():
                Select(model_sel).select_by_value("qwen3coder_s")
        except Exception:
            print("⚠️  Could not select model; proceeding with default.")

        prompt_el = wait.until(EC.presence_of_element_located((By.ID, "prompt")))
        prompt_el.clear()
        prompt_el.send_keys(instruction)

        gen_btn = wait.until(EC.element_to_be_clickable((By.ID, "submit-btn")))
        gen_btn.click()

        print("Waiting for backend (max. 30 min)…")
        time.sleep(TIMEOUT_MIN * 60)

        # Retrieve ZIP path from log file
        if os.path.isfile(LAST_ZIP_LOG_PATH):
            with open(LAST_ZIP_LOG_PATH, "r", encoding="utf-8") as f:
                last_zip = f.read().strip()
            if last_zip and os.path.isfile(last_zip):
                dest = os.path.join(output_dir, f"{test_id}.zip")
                shutil.copy(last_zip, dest)
                print(f"Copied output zip to: {dest}")
            os.remove(LAST_ZIP_LOG_PATH)

    finally:
        driver.quit()


# ──────────────────────────────────────────────────────────────────────────────
# Prompt template
# ──────────────────────────────────────────────────────────────────────────────
fullstack_prompt_template = """
Create a website repository based on the given user instruction with these rules:
1. If the site needs dynamic data, include:
   - A frontend that fetches all data from backend APIs. No hard-coded or mock data.
   - A backend that connects to an external PostgreSQL database using these exact
     environment variables:
       DB_HOST=localhost, DB_PORT=5432, DB_USERNAME=myappuser,
       DB_PASSWORD=myapppassword, DB_NAME=myapp.
2. If the site is strictly static (e.g., marketing or documentation), a backend is not required.
3. Configure the repository's `package.json` so that
   - `npm run install:all` installs both FE & BE, and
   - `npm run dev` starts both concurrently.

user instruction: {instruction}
""".strip()


# ──────────────────────────────────────────────────────────────────────────────
# Main driver
# ──────────────────────────────────────────────────────────────────────────────
def main() -> None:
    in_file = r"data\test.json"
    with open(in_file, "r", encoding="utf-8") as f:
        datas = json.load(f)

    for data in tqdm(datas):
        test_id = data["id"]
        print(f"\n================  Running test {test_id}  ================\n")

        if os.path.isfile(os.path.join(OUTPUT_DIR, f"{test_id}.zip")):
            print("Result already exists → skipping.")
            continue

        # ─── set up Postgres via Docker ───────────────────────────────
        working_dir = os.path.join(WORKING_DIR, test_id)
        log_dir = os.path.join(LOG_DIR, test_id)
        compose_path = os.path.join(log_dir, "docker-compose.yml")
        db_dir = os.path.join(log_dir, "db")
        DB_PORT = 5432

        create_docker_compose_file(
            working_dir, log_dir, compose_path, db_dir, db_port=DB_PORT
        )
        stop_docker_containers(compose_path)
        free_docker_port(DB_PORT)
        start_docker_containers(compose_path)

        # ─── start client-app service ────────────────────────────────
        client_proc = _start_client_app()
        try:
            wait_until_client_ready(timeout_sec=60)
        except TimeoutError as e:
            _stop_client_app(client_proc)
            raise RuntimeError(
                "Client app failed to start; aborting this sample."
            ) from e

        # ─── run Selenium interaction ────────────────────────────────
        prompt = fullstack_prompt_template.format(instruction=data["instruction"])
        try:
            run_single_instruction(
                prompt,
                test_id=test_id,
                download_path=DOWNLOAD_PATH,
                output_dir=OUTPUT_DIR,
            )
        finally:
            # Always stop client & DB, even on error
            _stop_client_app(client_proc)
            stop_docker_containers(compose_path)

        # ─── cool-down before next sample ─────────────────────────────
        print(f"Waiting {WAIT_AFTER_STOP_SEC}s before next sample…")
        time.sleep(WAIT_AFTER_STOP_SEC)


if __name__ == "__main__":
    main()