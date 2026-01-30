import json
import os
from argparse import ArgumentParser

# Import the function from remove_node_modules.py
from automatic_web_gen import automatic_web_gen
from remove_invalid_through_extract import process_directory

fullstack_prompt_template = """Create a website repository based on the given user instruction with these rules: 1. If the site needs dynamic data, include:   - A frontend that fetches all data from backend APIs. No hard-coded or mock data is allowed.   - A backend that connects to an external PostgreSQL database using these exact environment variables:  DB_HOST=localhost, DB_PORT=5432, DB_USERNAME=myappuser, DB_PASSWORD=myapppassword, DB_NAME=myapp. Every data operation must hit this database.    2. If the site is strictly static (e.g., marketing or documentation), a backend is not required.    3. Configure the repository's `package.json` file so that the command `npm run install:all` can install dependencies for both the frontend and the backend, and `npm run dev` can concurrently start the frontend and the backend services.    user instruction: {instruction}"""

def main():
    parser = ArgumentParser(description="Process JSONL file and generate web content.")
    parser.add_argument("--provider", default="OpenAILike", help="Provider name")
    parser.add_argument("--desired_model", default="Qwen2.5-Coder-32B-Instruct", help="Desired model path")
    parser.add_argument("--jsonl_path", default="data/test.jsonl", help="Path to the JSONL file")
    parser.add_argument("--url", default="http://localhost:5173/", help="bolt.diy url")
    parser.add_argument("--tag", default="", help="bolt.diy url")
    args = parser.parse_args()
    # Adjust these if you want different defaults
    provider = args.provider
    desired_model = args.desired_model
    url = args.url

    download_dir = f"downloads/{provider}/{os.path.basename(desired_model)}_{os.path.basename(args.jsonl_path).split('.')[0]}{args.tag}".replace(":", "_")

    # Replace with the actual path to the jsonl file
    jsonl_path = args.jsonl_path

    # Ensure the download_dir exists (optional)
    os.makedirs(download_dir, exist_ok=True)
    process_directory(download_dir)  # Clean up the download directory first

    idx = 1
    # Read the JSONL file line by line
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue  # Skip empty lines if any

            record = json.loads(line)
            instruction = record.get("instruction", "")
            
            prompt = fullstack_prompt_template.format(instruction=instruction)

            # Call automatic_web_gen for each record
            automatic_web_gen(
                idx=idx,
                instruction=prompt,
                download_dir=download_dir,
                url=url,
                desired_model=desired_model,
                provider=provider
            )

            idx += 1

if __name__ == "__main__":
    main()
