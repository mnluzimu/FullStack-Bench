import os
import platform
import time
import json
from tqdm import tqdm
from dotenv import load_dotenv
load_dotenv()

from pydantic import SecretStr

from openhands.sdk import (
    LLM,
    Conversation,
    RemoteConversation,
    get_logger,
)
from openhands.tools.preset.default import get_default_agent
from openhands.workspace import DockerWorkspace

import subprocess, pathlib

# ensure host dir is writable BEFORE starting Docker
WORKSPACE_ROOT = "baselines/openhands/workspaces_root"
TAG = ""
MAX_ITERATIONS = 400
RUN_NAME = f"Openhands_{os.getenv('LLM_MODEL').replace('\\', '-')}_iter{MAX_ITERATIONS}"
RUN_DIR = os.path.join(WORKSPACE_ROOT, RUN_NAME)
TEST_FILE = "data/FullStack-Bench.jsonl"
LOG_FILE = os.path.join(RUN_DIR, "log.jsonl")

logger = get_logger(__name__)

# 1) Ensure we have LLM API key
api_key = os.getenv("LLM_API_KEY")
assert api_key is not None, "LLM_API_KEY environment variable is not set."

llm = LLM(
    usage_id="agent",
    model=os.getenv("LLM_MODEL"),
    base_url=os.getenv("LLM_BASE_URL"),
    api_key=SecretStr(api_key),
)


def load_jsonl(in_file):
    datas = []
    with open(in_file, "r", encoding="utf-8") as f:
        for line in f:
            datas.append(json.loads(line))
    return datas


def save_jsonl(datas, out_file, mode="w"):
    with open(out_file, mode, encoding="utf-8") as f:
        for data in datas:
            f.write(json.dumps(data) + "\n")


def detect_platform():
    """Detects the correct Docker platform string."""
    machine = platform.machine().lower()
    if "arm" in machine or "aarch64" in machine:
        return "linux/arm64"
    return "linux/amd64"


def process_single(mount_dir, instruction):
    if not os.path.exists(mount_dir):
        os.makedirs(mount_dir, exist_ok=True)
    host_dir = pathlib.Path(mount_dir)
    if host_dir.exists():
        # change to uid/gid 1000 which is what the image uses
        subprocess.run(["sudo", "chown", "-R", "10001:10001", str(host_dir)], check=True)
    postgres_host_dir = os.path.join(mount_dir, "db")

    # create prompt
    fullstack_prompt_template = """Create a website repository based on the given user instruction with these rules: 1. If the site needs dynamic data, include:   - A frontend that fetches all data from backend APIs. No hard-coded or mock data is allowed.   - A backend that connects to an external PostgreSQL database using these exact environment variables:  DB_HOST=localhost, DB_PORT=5432, DB_USERNAME=myappuser, DB_PASSWORD=myapppassword, DB_NAME=myapp. Every data operation must hit this database.    2. If the site is strictly static (e.g., marketing or documentation), a backend is not required.    3. Configure the repository's `package.json` file so that the command `npm run install:all` can install dependencies for both the frontend and the backend, and `npm run dev` can concurrently start the frontend and the backend services.    user instruction: {instruction}"""
    prompt = fullstack_prompt_template.format(instruction=instruction)

    with DockerWorkspace(
        # use pre-built image for faster startup
        server_image="luzimu/openhands-postgres:latest",
        bind_mounts=[
            f"{postgres_host_dir}:/var/lib/postgresql/17/main",
            # you can add more mounts here
        ],
        platform=detect_platform(),
        mount_dir=mount_dir,
        working_dir="/workspace",
    ) as workspace:
        # 3) Create agent
        agent = get_default_agent(
            llm=llm,
            cli_mode=True,
        )

        # 4) Set up callback collection
        received_events: list = []
        last_event_time = {"ts": time.time()}

        def event_callback(event) -> None:
            event_type = type(event).__name__
            logger.info(f"🔔 Callback received event: {event_type}\n{event}")
            received_events.append(event)
            last_event_time["ts"] = time.time()

        conversation = Conversation(
            agent=agent,
            workspace=workspace,
            callbacks=[event_callback],
            max_iteration_per_run=MAX_ITERATIONS,
        )
        assert isinstance(conversation, RemoteConversation)

        try:
            logger.info(f"\n📋 Conversation ID: {conversation.state.id}")

            logger.info("📝 Sending message...")
            conversation.send_message(prompt)
            logger.info("🚀 Running conversation...")
            conversation.run()
            logger.info("✅ First task completed!")
            logger.info(f"Agent status: {conversation.state.execution_status}")

            # Wait for events to settle (no events for 2 seconds)
            logger.info("⏳ Waiting for events to stop...")
            while time.time() - last_event_time["ts"] < 2.0:
                time.sleep(0.1)
            logger.info("✅ Events have stopped")

        finally:
            print("\n🧹 Cleaning up conversation...")
            conversation.close()


def main():
    test_datas = load_jsonl(TEST_FILE)

    if os.path.isfile(LOG_FILE):
        log_datas = load_jsonl(LOG_FILE)
        logged_ids = [data["id"] for data in log_datas]
        filtered_test_datas = []
        for test_data in tqdm(test_datas):
            if test_data["id"] not in logged_ids:
                filtered_test_datas.append(test_data)
        test_datas = filtered_test_datas

    for data in tqdm(test_datas):
        instruction = data["instruction"]
        sample_id = data["id"]
        mount_dir = os.path.join(RUN_DIR, sample_id)

        print(f"Running sample {sample_id}")
        process_single(mount_dir, instruction)
        save_jsonl([data], LOG_FILE, mode="a")


if __name__ == "__main__":
    main()
