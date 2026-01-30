import os
import base64
import mimetypes
from typing import List

# --- OpenAI ------------------------------------------------------------------
import openai
from openai import OpenAI

from dotenv import load_dotenv
load_dotenv()  # take environment variables from .env file

openai_client = OpenAI(
    # put your OpenAI / proxied key here or read from env
    api_key=os.getenv("OPENAILIKE_VLM_API_KEY"),
    # if you use a proxy such as https://platform.llmprovider.ai
    base_url=os.getenv("OPENAILIKE_VLM_BASE_URL"),
)

print()

# --- Anthropic (Claude) ------------------------------------------------------
import anthropic

anthropic_client = anthropic.Anthropic(
    # export ANTHROPIC_API_KEY="..."
    api_key="sk-TjuuHBy4oQhNK0zZHYZx7Z53UOimglBqvA22H4n128D06f3403374a718530D1C09f106bE1",
    base_url="https://platform.llmprovider.ai"
)

# -----------------------------------------------------------------------------


from prompt import appearance_prompt   # ← your prompt template stays unchanged


def _encode_image(path: str) -> str:
    """Base64-encode an image file."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _mime_type(path: str) -> str:
    """Guess the MIME type (defaults to image/png)."""
    mtype, _ = mimetypes.guess_type(path)
    return mtype or "image/png"


def _build_openai_payload(base64_imgs: List[str], prompt: str):
    user_content = [{"type": "text", "text": prompt}]
    for b64, img_path in base64_imgs:
        user_content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{_mime_type(img_path)};base64,{b64}",
                },
            }
        )
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": user_content},
    ]
    return messages


def _build_anthropic_payload(base64_imgs: List[str], prompt: str):
    # Claude vision format: {"type":"image","source":{"type":"base64",...}}
    content = [{"type": "text", "text": prompt}]
    for b64, img_path in base64_imgs:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": _mime_type(img_path),
                    "data": b64,
                },
            }
        )
    messages = [{"role": "user", "content": content}]
    return messages


def get_score_result(
    image_paths: List[str],
    instruction: str,
    model: str = "gpt-4o-mini",
    max_tokens: int = 1024,
):
    """
    Calls either the OpenAI or Anthropic Chat API depending on the model name.
    """
    # Read & encode all screenshots once
    base64_imgs = [( _encode_image(p), p) for p in image_paths]

    prompt = appearance_prompt.format(instruction=instruction)

    # ------------------------------------------------------------------ OpenAI
    if not model.lower().startswith("claude"):
        messages = _build_openai_payload(base64_imgs, prompt)
        resp = openai_client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content

    # --------------------------------------------------------------- Anthropic
    messages = _build_anthropic_payload(base64_imgs, prompt)
    resp = anthropic_client.messages.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        system="You are a helpful assistant.",
    )

    # `resp.content` is a list of blocks; keep only text parts.
    return "".join(
        block.text for block in resp.content if block.type == "text"
    )


# -----------------------------------------------------------------------------


if __name__ == "__main__":
    image_paths = [
        "/mnt/cache/k12_data/WebGen-Agent2/logs_root/model-Qwen3-Coder-30B-A3B-Instruct_hist-100_iter-400_compress-0.5_val-1_sum-5_v8/results/task000001_6/screenshot1.png",
    ]

    instruction = (
        "Please implement a short-term apartment rental website for showcasing "
        "and renting apartments. The website should have functionalities for "
        "searching, filtering, and booking apartments. Users should be able to "
        "browse different types of apartments, search and filter apartments "
        "that meet their criteria, book selected apartments, and view booking "
        "records. Use linen as the screen background and maroon for component "
        "highlights."
    )

    print(
        get_score_result(
            image_paths,
            instruction,
            model=os.getenv("VLM_MODEL"),
        )
    )