"""
ServiceTestTool – start a local service, probe its HTTP API, capture console
output, and return a concise summary (optionally compressed by an LLM).

Dependencies:
  * requests         – pip install requests
  * psutil (optional)– pip install psutil  (falls back to `lsof` if missing)
  * openai (optional)– pip install openai  (only needed when `openai_api_key`
                      is provided so the tool can shrink very long logs)
"""
from __future__ import annotations

import os
import shlex
import json
import time
import subprocess
import textwrap
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
import requests
import re
import uuid
import libtmux

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_utils import llm_generation
from .base_tool import BaseTool
from .tool_types import ToolKind
from .tool_utils import kill_service_on_port

# --------------------------------------------------------------------------- #
# Utilities                                                                   #
# --------------------------------------------------------------------------- #

MAX_LOG_CHARS_BEFORE_SUMMARISE = 10000            # tweak as needed
SERVICE_STARTUP_TIMEOUT        = 180               # seconds
LOG_POLL_INTERVAL              = 0.4              # seconds


def get_backend_message_compression_prompt(long_text: str) -> str:
    return f"""You are a technical log compressor. Your task is to process the output by performing a lossy compression that **strictly preserves factual data** while removing redundant noise.

**Your directive is to TRANSFORM the text, not SUMMARIZE it.**

### **CRITICAL RULES:**
1.  **Preserve:** All error codes, status messages, unique identifiers, file paths, URLs, key css styles, and any non-repetitive text.
2.  **Remove:** repetitive errors or warnings, and large blocks of minified code. Also remove any useless noises.
3.  **Condense:** Replace long, repetitive internal state objects (e.g., `self.__next_f.push([1, ...]`) with a clear placeholder like `<!-- [NEXT INTERNAL STATE...] -->` or `[Turbopack dev scripts truncated]`.
4.  **Do NOT** add external analysis, "Actionable" items, or guesses. Only reflect the content that is present in the output.
5.  The final output should be a shortened, yet still technical, version of the original text.

**Now, compress the following output:**

Output to compress:
{long_text}"""


def _invoke_llm_summariser(long_text: str) -> str:
    """
    Shrinks `long_text` with the OpenAI ChatCompletion API, returning
    a concise summary that highlights errors / stack-traces.
    """
    if len(long_text) > MAX_LOG_CHARS_BEFORE_SUMMARISE:
        try:
            prompt = get_backend_message_compression_prompt(long_text)
            messages = [{"role": "system", "content": "You are an expert at compressing text."}, {"role": "user", "content": prompt}]
            response = llm_generation(messages, model=model)
            compressed_text = response.get("content", "")
        except Exception as e:
            print(f"Error during LLM compression: {str(e)}\n\nFalling to naive compression...")
            compressed_text = long_text[-MAX_LOG_CHARS_BEFORE_SUMMARISE:]
        is_compressed = True
    else:
        compressed_text = long_text
        is_compressed = False

    return compressed_text, is_compressed


def _host_variants(url: str) -> List[str]:
    """
    Return host:port variants that normalise `localhost` and `127.0.0.1`.

    Example
    -------
    >>> _host_variants('http://localhost:3001/api/stocks/AAPL')
    ['localhost:3001', '127.0.0.1:3001']
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port

    # If the hostname is neither localhost nor 127.0.0.1, just return it
    if host not in {"localhost", "127.0.0.1"}:
        return [f"{host}:{port}"]

    alt_host = "127.0.0.1" if host == "localhost" else "localhost"
    return [f"{host}:{port}", f"{alt_host}:{port}"]


# CSI / SGR / cursor-movement / colour sequences (same as before, very fast).
_CSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

# OSC sequences: ESC ] … BEL or ESC ] … ESC \
_OSC_RE = re.compile(r"\x1B](?:[^\x07\x1b]*?)(?:\x07|\x1B\\)")

# ST / PM / APC, Device-control, etc.  (rare but easy to strip)
_MISC_RE = re.compile(r"\x1B[][PX^_].*?\x1B\\", re.DOTALL)

# ──────────────────────────────────────────────────────────────────────────────
def clean_console(data: Union[str, bytes]) -> str:
    """
    Strip NUL bytes, ANSI/VT-100 control sequences, and excessive blank lines
    from captured terminal output.  Works whether *data* comes straight from a
    log file (contains real ESC bytes) or from a JSON blob (contains literal
    ``\\u001b`` sequences).

    Parameters
    ----------
    data : str | bytes
        Raw console output.

    Returns
    -------
    str
        Readable, plain-text log.
    """
    # 0. Normalise to *str*.
    if isinstance(data, bytes):
        data = data.decode("utf-8", errors="replace")

    # 1. Drop NUL / NULL padding (both literal and JSON-escaped forms).
    data = data.replace("\x00", "").replace("\\u0000", "")

    # 2. If we only have JSON-escaped ESC codes (\\u001b) but no real ones,
    #    convert them into real ESC so that the regexes can match.
    if "\\u001b" in data and "\x1b" not in data:
        data = bytes(data, "utf-8").decode("unicode_escape")

    # 3. Strip all kinds of ANSI escape sequences.
    data = _CSI_RE.sub("", data)
    data = _OSC_RE.sub("", data)
    data = _MISC_RE.sub("", data)

    # 4. Tidy up line endings and whitespace noise.
    data = data.replace("\r", "")
    data = re.sub(r"\n{3,}", "\n\n", data)   # collapse 3+ blank lines → 2
    data = data.lstrip("\n")                 # no leading blank lines

    return data


def _prepare_payload(raw, headers):
    """
    Decide whether to pass `json=` or `data=` to requests.request.

    Returns
    -------
    dict
        { "json": obj }          if raw is a dict/list
        { "json": obj }          if raw is a JSON string that parses cleanly
        { "data": raw }          otherwise
    dict
        merged headers (may add Content-Type)
    """
    if raw is None:
        return {}, headers

    # 1. Native JSON object → send with json=
    if isinstance(raw, (dict, list)):
        return {"json": raw}, headers

    # 2. String → try to parse
    if isinstance(raw, str):
        try:
            obj = json.loads(raw)
            # parsed! treat it as JSON
            return {"json": obj}, headers
        except json.JSONDecodeError:
            # not JSON → fall through to send as-is
            pass

    # 3. Anything else → send as data=
    # ensure we don't double-encode; set content-type if missing
    if "content-type" not in {k.lower() for k in headers.keys()}:
        headers["Content-Type"] = "application/json"  # or text/plain – pick what fits

    return {"data": raw}, headers


# --------------------------------------------------------------------------- #
# The Tool                                                                    #
# --------------------------------------------------------------------------- #


class BackendTestTool(BaseTool):
    """
    Tool that:
      1. Frees requested ports.
      2. Starts a service (`start_command`) in `directory_path`.
      3. Waits until `url` appears in log.
      4. Sends an HTTP request to `url` (relative, assumed `http://127.0.0.1:<first-port>`).
      5. Captures stdout/stderr into a log file.
      6. Generates a summary of parameters, HTTP response, and relevant log
         output (optionally compressed by an LLM).
    """

    Name = "backend_test"

    def __init__(self, working_dir: str, log_dir: str):
        super().__init__(
            self.Name,
            """Specialized backend testing tool. Sends a single HTTP request to the supplied URL, then returns the response to the request.

Expectation for required parameters  
- `url` MUST be a full URL (`http(s)://host:port/path`). This URL is invoked for the HTTP request.  
- `method` MUST be a standard HTTP verb: `"GET"`, `"POST"`, `"PUT"`, `"PATCH"` or `"DELETE"`.

Optional parameters  
- `data` – JSON-serialisable body (ignored for `GET`).  
- `headers` – additional HTTP headers.""",
            {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": (
                            "Full URL to call – must include protocol, host, port and path, "
                            "e.g. 'http://localhost:8080/health'."
                        ),
                    },
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                    },
                    "data": {
                        "description": "JSON-serialisable body to send (optional).",
                    },
                    "headers": {
                        "type": "object",
                        "description": "Optional HTTP headers.",
                    },
                },
                "required": [
                    "url",
                    "method",
                ],
            },
            ToolKind.EXECUTE,
        )
        self.working_dir = working_dir
        self.log_dir = log_dir

    # --------------------------------------------------------------------- #
    # Validation                                                             #
    # --------------------------------------------------------------------- #

    def validate_params(self, params: Dict[str, Any]) -> Optional[str]:
        err = super().validate_params(params)
        if err:
            return err

        return None

    # --------------------------------------------------------------------- #
    # Execution                                                              #
    # --------------------------------------------------------------------- #

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        validation_error = self.validate_params(params)
        if validation_error:
            return {
                "llmContent": f"Error: {validation_error}",
                "returnDisplay": f"Error: {validation_error}",
                "error": {"type": "invalid_tool_params", "message": validation_error},
            }

        # Extract
        full_url: str = params["url"]
        method: str = params["method"].upper()
        data = params.get("data")
        headers = params.get("headers") or {}

        try:
            payload, headers = _prepare_payload(data, headers)

            resp = requests.request(
                method,
                full_url,
                headers=headers,
                timeout=30,
                **payload           # json=…  or  data=… chosen automatically
            )
            resp_text = resp.text
            status = resp.status_code
        except Exception as exc:  # noqa: BLE001
            resp_text = f"Request failed: {exc}"
            status = None

        resp_summary, resp_compressed = _invoke_llm_summariser(resp_text)

        # 7. Build summary
        summary_dict = {
            "url": full_url,
            "method": method,
            "data": data,
            "status_code": status,
            "resp_compressed": resp_compressed,
            "resp_log": resp_summary[:500],
        }

        llm_readable = f"""Service test completed
- Request: {method} {full_url}
- Data: {data}
- Response Status Code: {status}
- Response{' (compressed)' if resp_compressed else ''}: {resp_summary}""".strip()

        return {
            "llmContent": llm_readable,
            "returnDisplay": json.dumps(summary_dict, indent=2),
        }