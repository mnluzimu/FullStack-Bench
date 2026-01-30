#!/usr/bin/env python
"""
Unified chat wrapper that understands OpenAI *and* Anthropic tool calling.

───────────────────────────────────────────────────────────────────────────────
USAGE
-----

1.  Declare your tools (OpenAI/Claude style JSON-Schema):
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Return tomorrow's weather in a city.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city":  { "type": "string" },
                            "unit":  { "type": "string", "enum": ["celsius","fahrenheit"], "default": "celsius" }
                        },
                        "required": ["city"],
                        "additionalProperties": False
                    }
                }
            }
        ]

2.  Register the python implementation:
        def get_weather(city:str, unit:str="celsius"): ...
        registry = { "get_weather": get_weather }

3.  Call:
        assistant_msg = chat_with_tools(
            messages=[{"role":"user","content":"Will it be warm enough for shorts in Paris tomorrow?"}],
            model="gpt-4o-mini",
            tools=tools,
            tool_registry=registry
        )
───────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import os, sys, base64, binascii, json, inspect
from typing import Callable, Any, Dict, List

from dotenv import load_dotenv
from openai import OpenAI
from anthropic import Anthropic

# ── ENV / SDK setup ───────────────────────────────────────────────────────────
load_dotenv()
project_root = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

openai_client = OpenAI(
    api_key=os.environ["OPENAILIKE_API_KEY"],
    base_url=os.environ["OPENAILIKE_BASE_URL"],
)

# print(os.environ["OPENAILIKE_API_KEY"])
# print(os.environ["OPENAILIKE_BASE_URL"])

anthropic_client = Anthropic(
    api_key=os.environ["ANTHROPIC_API_KEY"],
    base_url=os.environ["ANTHROPIC_BASE_URL"],
)

# ── Utility: detect image MIME (unchanged) ────────────────────────────────────
def _detect_media_type(b64: str, fallback: str = "image/jpeg") -> str:        # ... unchanged ...
    try:
        hdr = base64.b64decode(b64[:64], validate=False)
    except binascii.Error:
        return fallback
    if hdr.startswith(b"\xFF\xD8\xFF"): return "image/jpeg"
    if hdr.startswith(b"\x89PNG\r\n\x1A\n"): return "image/png"
    if hdr.startswith(b"GIF87a") or hdr.startswith(b"GIF89a"): return "image/gif"
    if hdr[0:4] == b"RIFF" and hdr[8:12] == b"WEBP": return "image/webp"
    return fallback

# ── OpenAI → Claude message conversion (unchanged) ────────────────────────────
def _convert_to_anthropic(messages: List[dict]) -> tuple[str|None, List[dict]]:    # ... unchanged ...
    converted, system_text = [], None
    for msg in messages:
        role = msg["role"]
        if role == "system": system_text = msg["content"]; continue
        block: Dict[str, Any] = {"role": role, "content": []}
        if isinstance(msg["content"], str):
            block["content"].append({"type": "text", "text": msg["content"]})
            converted.append(block); continue
        for part in msg["content"]:
            if part["type"] == "text":
                block["content"].append({"type":"text","text":part["text"]})
            elif part["type"] == "image_url":
                url = part["image_url"]["url"]
                media_prefix, b64_data = url.split(";base64,",1)
                media_type = _detect_media_type(b64_data, fallback=media_prefix.replace("data:",""))
                block["content"].append({"type":"image","source":{"type":"base64","media_type":media_type,"data":b64_data}})
        converted.append(block)
    return system_text, converted

# ──────────────────────────────────────────────────────────────────────────────
#  LOW-LEVEL ONE-SHOT CALL (no tool handling yet)
# ──────────────────────────────────────────────────────────────────────────────
def _raw_chat_completion(messages: List[dict], model: str, **kwargs) -> dict:
    """
    Fire a single request to the chosen provider and return the *assistant*
    message object exactly as the provider produced it.
    """
    is_anthropic = any(tag in model.lower() for tag in ("anthropic", "claude"))
    if is_anthropic:
        # Anthropic requires system prompt separated and `max_tokens`.  
        system_text, claude_msgs = _convert_to_anthropic(messages)
        resp = anthropic_client.messages.create(
            model=model,
            system=system_text,
            messages=claude_msgs,
            max_tokens=kwargs.pop("max_tokens", 8192),
            **kwargs,
        )
        # Re-create an OpenAI-style assistant message dict so the rest of the
        # pipeline can treat both vendors identically.
        content_block = resp.content[0]        # could be text or tool_use
        assistant_msg = {"role":"assistant"}
        if content_block.type == "text":
            assistant_msg["content"] = content_block.text
        elif content_block.type == "tool_use":            # Claude tool call
            assistant_msg["content"] = None
            assistant_msg["tool_calls"] = [{
                "id": content_block.id,
                "type": "function",
                "function": {
                    "name": content_block.name,
                    "arguments": json.dumps(content_block.arguments)
                }
            }]
        assistant_msg["_finish_reason"] = resp.stop_reason or "stop"
        return assistant_msg

    # ── OpenAI route ─────────────────────────────────────────────────────────
    resp = openai_client.chat.completions.create(
        model=model,
        messages=messages,
        **kwargs,
    )
    msg = resp.choices[0].message

    # Pydantic v2 (new) → .model_dump();  fall back to .dict() for v1
    try:
        assistant_msg = msg.model_dump(exclude_none=True)
    except AttributeError:
        assistant_msg = msg.dict(exclude_none=True)

    assistant_msg["_finish_reason"] = resp.choices[0].finish_reason
    return assistant_msg

# ──────────────────────────────────────────────────────────────────────────────
#  HIGH-LEVEL LOOP  —  AUTO-EXECUTE TOOLS UNTIL DONE
# ──────────────────────────────────────────────────────────────────────────────
ToolRegistry = Dict[str, Callable[..., Any]]

def _execute_tool(tool_name:str, arguments_json:str|dict, registry:ToolRegistry) -> str:
    if tool_name not in registry:
        raise ValueError(f"Tool '{tool_name}' not found in registry.")
    fn = registry[tool_name]
    if isinstance(arguments_json, str):
        arguments = json.loads(arguments_json or "{}")
    else:
        arguments = arguments_json
    # simple signature check
    sig = inspect.signature(fn)
    bound = sig.bind_partial(**arguments)
    bound.apply_defaults()
    result = fn(**bound.arguments)
    # must be string for both OpenAI and Anthropic
    return result if isinstance(result,str) else json.dumps(result, ensure_ascii=False)


def llm_generation(messages: list[dict], model: str, **kwargs) -> dict:
    """
    Send ONE chat request to OpenAI or Anthropic and return the *assistant*
    message as a plain Python dict.

    The returned dict is normal OpenAI format:
        {
          "role": "assistant",
          "content": "... or None ...",
          "tool_calls": [ ... ]            # present only if the model requested a tool
        }

    The structure is identical whether the underlying provider is OpenAI *or*
    Claude, so your downstream code can inspect `message["tool_calls"]`
    without caring which model you used.
    """
    is_anthropic = any(tag in model.lower() for tag in ("anthropic", "claude"))

    # ── Anthropic branch ──────────────────────────────────────────────────────
    if is_anthropic:
        sys_msg, claude_msgs = _convert_to_anthropic(messages)

        resp = anthropic_client.messages.create(
            model=model,
            system=sys_msg,
            messages=claude_msgs,
            max_tokens=kwargs.pop("max_tokens", 8192),
            **kwargs,
        )

        block = resp.content[0]          # first content block
        assistant = {"role": "assistant"}

        if block.type == "text":                     # normal text reply
            assistant["content"] = block.text

        elif block.type == "tool_use":               # Claude tool call
            assistant["content"] = None
            assistant["tool_calls"] = [{
                "id":   block.id,
                "type": "function",
                "function": {
                    "name":      block.name,
                    "arguments": json.dumps(block.arguments)
                }
            }]

        return assistant

    # monkey patch: if houxing's model, change model name to "model"
    if model == "/mnt/cache/code/models/Qwen3-Coder-480B-A35B-Instruct-FP8":
        model = "model"

    # ── OpenAI branch ─────────────────────────────────────────────────────────
    resp = openai_client.chat.completions.create(
        model=model,
        messages=messages,
        **kwargs,
    )
    msg = resp.choices[0].message

    # Pydantic v2 (.model_dump) or v1 (.dict)
    try:
        assistant = msg.model_dump(exclude_none=True)
    except AttributeError:                # old SDK / pydantic-v1
        assistant = msg.dict(exclude_none=True)

    return assistant

# ──────────────────────────────────────────────────────────────────────────────
#  DEMO
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    conversation = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Will it be warm enough for shorts in Paris tomorrow?"}
    ]

    assistant_msg = llm_generation(
        messages=conversation,
        model="/mnt/cache/code/models/Qwen3-Coder-480B-A35B-Instruct-FP8",
        # model="deepseek-chat",
        # model="deepseek-v3-250324",
        tools=[   # optional: declare your tools so the model can call them
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get tomorrow's weather for a city",
                    "parameters": {
                        "type": "object",
                        "properties": { "city": { "type": "string" } },
                        "required": ["city"]
                    }
                }
            }
        ]
    )

    # ------------------------------------------------------------------------
    #  Now YOU decide what to do:
    #    • If assistant_msg has no "tool_calls" → just print the text.
    #    • If it contains tool_calls           → parse, execute, etc.
    # ------------------------------------------------------------------------
    if "tool_calls" in assistant_msg:
        print("Model asked to call a tool:")
        print(json.dumps(assistant_msg["tool_calls"], indent=2))
    else:
        print("Assistant:", assistant_msg["content"])