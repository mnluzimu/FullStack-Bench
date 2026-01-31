import os
import base64

import sys
project_root = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from prompts import system_prompt
from utils import vlm_generation

import json
import re
from typing import Dict

def parse_screenshot_output(output_str: str) -> Dict[str, object]:
    # 1) Extract JSON block (handles optional Markdown/code fences)
    match = re.search(r"\{.*\}", output_str, flags=re.DOTALL)
    if not match:
        print("No JSON object found in the input string.")

    json_str = match.group(0)

    data = {}
    # 2) Parse JSON into Python dict
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}")

    # 3) Basic validation (optional but useful)
    required_keys = {"is_error", "error_message", "screenshot_description"}
    missing = required_keys - data.keys()
    if missing:
        print(f"Missing required key(s): {', '.join(missing)}")

    return data


def encode_image(image_path):
  with open(image_path, "rb") as image_file:
    return base64.b64encode(image_file.read()).decode('utf-8')


screenshot_prompt = """You are given a single website screenshot as input.

**Task**

1. Examine the screenshot closely for any visual or runtime errors (e.g., “404 Not Found”, stack traces, missing styles, blank areas).
2. Decide whether the screenshot *shows a rendering or runtime error*.  
   - If **yes**, set `"is_error": true`, extract or paraphrase the visible error message(s) into `"error_message"`, and leave `"screenshot_description"` empty.
   - If **no**, set `"is_error": false`, leave `"error_message"` as an empty string (`""`), and write a concise but thorough `"screenshot_description"` covering:
     - Overall layout (e.g., header / sidebar / footer, grid, flex, single‑column, etc.).
     - Key UI components (navigation bar, buttons, forms, images, cards, tables, modals, etc.).
     - Color scheme and visual style (dominant colors, light/dark theme, gradients, shadows).
     - Content and text visible (headings, labels, sample data).
     - Any notable design details (icons, spacing, font style) that help someone understand what the page looks like.

**Output format (valid JSON)**

```json
{
  "is_error": <boolean>,
  "error_message": "<string>",
  "screenshot_description": "<string>"
}
```

Return only this JSON object—no additional commentary, markdown, or code fences."""


def get_screenshot_description(image_path):
    base64_image = encode_image(image_path)
    messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant."
            },
            {
                "role": "user",
                "content":[
                {
                    "type": "text",
                    "text": screenshot_prompt
                },
                {
                    "type": "image_url",
                    "image_url":{
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                },
                ]
            }
        ]

    result = vlm_generation(messages, "/mnt/cache/sharemath/models/Qwen/Qwen2.5-VL-32B-Instruct")
    data = parse_screenshot_output(result)

    return data