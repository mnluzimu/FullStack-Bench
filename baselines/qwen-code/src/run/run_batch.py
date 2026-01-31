import json
import os
from tqdm import tqdm
import traceback
from dotenv import load_dotenv
load_dotenv()

from start_qwen_cli import execute_qwen_cli
from sandbox import create_docker_compose_file, start_docker_containers, stop_docker_containers, free_docker_port

TIMEOUT = 1800

def load_jsonl(in_file):
    datas = []
    with open(in_file, "r", encoding="utf-8") as f:
        for line in f:
            datas.append(json.loads(line))
    return datas


def save_jsonl(datas, out_file, mode="w"):
    with open(out_file, mode, encoding="utf-8") as f:
        for data in tqdm(datas):
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
            
            
fullstack_prompt_template = "Create a website repository based on the given user instruction with these rules: 1. If the site needs dynamic data, include:   - A frontend that fetches all data from backend APIs. No hard-coded or mock data is allowed.   - A backend that connects to an external PostgreSQL database using these exact environment variables:  DB_HOST=localhost, DB_PORT=5432, DB_USERNAME=myappuser, DB_PASSWORD=myapppassword, DB_NAME=myapp. Every data operation must hit this database.    2. If the site is strictly static (e.g., marketing or documentation), a backend is not required.    3. Configure the repository's `package.json` file so that the command `npm run install:all` can install dependencies for both the frontend and the backend, and `npm run dev` can concurrently start the frontend and the backend services.    4. Do not run `npm run dev` directly as it would block the process indefinitely.    user instruction: {instruction}"
    
        
def process_single(sample, log_dir_root, working_dir_root):
    log_dir = os.path.join(log_dir_root, sample["id"])
    working_dir = os.path.join(working_dir_root, sample["id"])
    
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(working_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "output.log")
    
    prompt = fullstack_prompt_template.format(instruction=sample["instruction"])
    
    compose_path = os.path.join(log_dir, f"webgen-agent_{sample['id']}", "docker-compose.yml")
    db_dir = os.path.join(log_dir, "db")
    DB_PORT = 5432
    create_docker_compose_file(working_dir, log_dir, compose_path, db_dir, db_port=DB_PORT)
    stop_docker_containers(compose_path)
    free_docker_port(DB_PORT)
    start_docker_containers(compose_path)

    try:
        execute_qwen_cli(
            prompt=prompt,
            working_dir=working_dir,
            model=os.environ["OPENAI_MODEL"],
            debug=True,
            output_format="text",
            approval_mode="yolo",
            all_files=False,
            show_memory_usage=False,
            auth_type="openai",
            openai_api_key=os.environ["OPENAI_API_KEY"],
            openai_base_url=os.environ["OPENAI_BASE_URL"],
            log_file_path=log_file,
            timeout=TIMEOUT,
        )
    except Exception as err:
        # Option A: one-liner (logs message AND traceback)
        logging.exception(
            "process_single failed for sample %s: %s", sample["id"], err
        )

        with open(os.path.join(log_dir, "error.trace"), "w") as fh:
            fh.write(traceback.format_exc())
    finally:
        stop_docker_containers(compose_path)
    
    
def main():
    test_file = os.path.abspath(r"data\WebGen-Bench_test-db-backend.jsonl")
    tag = "fullstack"
    log_dir_root = os.path.abspath(r"logs_root")
    working_dir_root = os.path.abspath(r"workspaces")
    run_name = f"{os.environ['OPENAI_MODEL']}_{tag}"

    log_dir_root = os.path.join(log_dir_root, run_name)
    working_dir_root = os.path.join(working_dir_root, run_name)
    finished_file = os.path.join(log_dir_root, "finished_samples.jsonl")
    
    samples = load_jsonl(test_file)
    if os.path.isfile(finished_file):
        finished_ids = [d["id"] for d in load_jsonl(finished_file)]
        filtered_samples = []
        for sample in samples:
            if sample["id"] not in finished_ids:
                filtered_samples.append(sample)
        samples = filtered_samples
    
    for sample in tqdm(samples):
        
        process_single(sample, log_dir_root, working_dir_root)
        save_jsonl([{"id": sample["id"]}], finished_file, mode="a")
        
        
if __name__ == "__main__":
    main()