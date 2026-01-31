"""
Selenium helper that

1.  opens one Chrome session with two windows
      • window 0 → http://localhost:5173/
      • window 1 → http://127.0.0.1:8003/
2.  offers  run_single_instruction()  which
      • (optionally) clicks  “Clear Cache”
      • pastes a prompt
      • presses the “Generate” button
      • keeps the browser alive for up-to 30 minutes so the
        backend has enough time to finish its job.

Tested with Selenium-4.x and Chrome-122+.  
Make sure a matching chromedriver is on PATH or set
the CHROMEDRIVER env-var to its location.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Dict, List
import shutil
import json
from tqdm import tqdm

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait, Select


# --------------------------------------------------------------------------- #
#                              browser helpers                                #
# --------------------------------------------------------------------------- #

BOLT_DIY_ADDRESS = "http://localhost:5173/"
TDDEV_CLIENT_ADDRESS = "http://127.0.0.1:8003/"
CHROME_BINARY = r"C:\Users\luzim\AppData\Local\Google\Chrome SxS\Application\chrome.exe"
DOWNLOAD_PATH = r"downloads\qwen3coder480B"
OUTPUT_DIR = r"outputs\qwen3coder480B"
LAST_ZIP_LOG_PATH = r"client\last_zip_path_log.txt"
TIMEOUT_MIN = 30

if not os.path.isdir(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

if not os.path.isdir(DOWNLOAD_PATH):
    os.makedirs(DOWNLOAD_PATH, exist_ok=True)

def _new_driver(download_path: str, chrome_binary: str | None = None) -> WebDriver:
    """
    Launch Chrome with custom download directory and (optionally) a specific
    executable path.
    """
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
        "profile.default_content_setting_values.automatic_downloads": 1
    }
    opts.add_experimental_option("prefs", prefs)

    opts.add_argument("--disable-popup-blocking")

    service = ChromeService()      # assumes chromedriver in PATH or webdriver-manager
    return webdriver.Chrome(service=service, options=opts)


def _open_two_windows(driver: WebDriver) -> List[str]:
    """
    Returns the list of window handles, index 0 for localhost:5173
    and index 1 for 127.0.0.1:8003
    """
    # first window
    driver.get(BOLT_DIY_ADDRESS)
    first_handle = driver.current_window_handle

    # second window
    driver.switch_to.new_window("window")
    driver.get(TDDEV_CLIENT_ADDRESS)
    second_handle = driver.current_window_handle

    return [first_handle, second_handle]


# --------------------------------------------------------------------------- #
#                              core function                                  #
# --------------------------------------------------------------------------- #

def run_single_instruction(
    instruction: str,
    test_id: str = "",
    download_path: str = "./downloads",
    output_dir: str = "./outputs",
    chrome_binary: str | None = CHROME_BINARY,
) -> None:
    """
    Drives the UI at  http://127.0.0.1:8003/  once.

    Parameters
    ----------
    instruction : str
        Prompt text that will be typed into the textarea.
    test_id : str
        Optional identifier – used only for debug screenshots.
    download_path : str
        Directory that Chrome will use as its default download folder.
    """
    driver = _new_driver(download_path, chrome_binary)
    win0, win1 = _open_two_windows(driver)

    try:
        # ――― switch to the second window (the Text Generation tool) ―――
        driver.switch_to.window(win1)

        wait = WebDriverWait(driver, 30)

        # 1)  Click “Clear Cache” if it is visible
        try:
            clear_btn = wait.until(
                EC.presence_of_element_located((By.ID, "clear-cache-btn"))
            )
            if clear_btn.is_displayed() and clear_btn.is_enabled():
                clear_btn.click()
                # page will reload – wait until the textarea is back
                wait.until(EC.staleness_of(clear_btn))
                wait.until(
                    EC.presence_of_element_located((By.ID, "prompt"))
                )
        except Exception:
            # Clear-cache button absent – totally fine
            pass

        try:
            model_select_el = wait.until(EC.presence_of_element_located((By.ID, "model")))
            if model_select_el.is_enabled():                       # may be disabled by cache lock
                Select(model_select_el).select_by_value("qwen3coder")
        except Exception:
            print("⚠️  Could not select model; proceeding with default.")

        # 2)  Fill the textarea
        prompt_el = wait.until(
            EC.presence_of_element_located((By.ID, "prompt"))
        )
        prompt_el.clear()
        prompt_el.send_keys(instruction)

        # 3)  Press the “Generate” button
        gen_btn = wait.until(
            EC.element_to_be_clickable((By.ID, "submit-btn"))
        )
        gen_btn.click()

        # 4)  Let the generation run for up-to 30 min.
        #     Replace this with a smarter wait condition if available.
        MAX_SECONDS = TIMEOUT_MIN * 60
        poll_interval = 5
        elapsed = 0
        print("Waiting for the backend to finish (30 min max)…")
        while elapsed < MAX_SECONDS:
            time.sleep(poll_interval)
            elapsed += poll_interval
            # If result box is non-empty you could break early here:
            # result_txt = driver.find_element(By.ID, "result").text.strip()
            # if result_txt and result_txt.lower() != "loading...":
            #     break

        with open(LAST_ZIP_LOG_PATH, "r", encoding="utf-8") as f:
            last_zip_path = f.read().strip()
            print(f"Last downloaded zip path: {last_zip_path}")
        if last_zip_path and os.path.isfile(last_zip_path):
            dest_path = os.path.join(OUTPUT_DIR, f"{test_id}.zip")
            shutil.copy(last_zip_path, dest_path)
            print(f"Copied output zip to: {dest_path}")

        # make sure to clean up the log file so next run starts fresh
        if os.path.isfile(LAST_ZIP_LOG_PATH):
            os.remove(LAST_ZIP_LOG_PATH)
    except Exception as e:
        print(f"❌  Error during run: {e}")
        exit(1)

    finally:
        # keep the browser for debugging?  comment out if unwanted
        driver.quit()
        pass


def main():
    in_file = r"data\test.json"
    with open(in_file, "r", encoding="utf-8") as f:
        datas = json.load(f)

    for data in tqdm(datas):
        print(f"Running test id: {data['id']}")
        prompt = data["instruction"]
        test_id = data["id"]
        if os.path.isfile(os.path.join(OUTPUT_DIR, f"{test_id}.zip")):
            print(f"Output for test id {test_id} already exists. Skipping.")
            continue
        run_single_instruction(prompt, test_id=test_id, download_path=DOWNLOAD_PATH, output_dir=OUTPUT_DIR)

# --------------------------------------------------------------------------- #
#                              example usage                                  #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    main()