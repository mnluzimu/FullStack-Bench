import json
import re

_JSON_BLOCK_RE = re.compile(r"```json(.*?)```", re.S)

def parse_json_response(raw_text: str):
    """
    Extract the list of data structures from the model's raw response.
    Returns [] if nothing could be parsed.
    """
    # 1) Prefer the fenced ```json ... ``` block
    match = _JSON_BLOCK_RE.search(raw_text)
    json_src = match.group(1).strip() if match else raw_text

    try:
        parsed = json.loads(json_src)
        return parsed
    except json.JSONDecodeError:
        pass  # fall through to next attempt

    # 2) Fallback: try to find a list-like string manually
    try:
        parsed = json.loads(re.search(r"\{.*\}", raw_text, re.S).group())
        return parsed
    except Exception:
        return {}