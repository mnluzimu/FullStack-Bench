"""
FrontendTestTool – run a GUI-agent (WebGen-Bench) E2E test against a local
front-end dev server.

Minimal external dependency
---------------------------
pip install webtester         # provides `WebAgentTester`
"""

from __future__ import annotations

import os
import re
import json
from typing import Dict, Any, List, Optional

import sys
import textwrap
import time
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .base_tool import BaseTool
from .tool_types import ToolKind
from .tool_utils import kill_service_on_port

from webtester import WebAgentTester

# --------------------------------------------------------------------------- #
# Helper: choose an incremental log dir                                       #
# --------------------------------------------------------------------------- #
_STEP_RX = re.compile(r"(\d+)_llm_response\.json")


def _next_index(base_dir: str) -> int:
    """
    Inspect *base_dir* for files named like '42_llm_response.json' and
    return the maximum index (integer). 0 if none exist.
    """
    try:
        nums = [
            int(m.group(1))
            for name in os.listdir(base_dir)
            if (m := _STEP_RX.match(name))
        ]
        return max(nums, default=0)
    except FileNotFoundError:
        return 0


# --------------------------------------------------------------------------- #
# The Tool                                                                    #
# --------------------------------------------------------------------------- #
class FrontendTestTool(BaseTool):
    """
    Spins up a front-end development server and asks WebGen-Bench’s
    visual-language agent to carry out the provided **instruction** in a
    headless browser.  The session finishes when the agent reports success or
    the site throws an uncaught console error.

    Returned object is exactly what `WebAgentTester.run_test()` yields:
    ```
    {
        "llmContent": "... full conversation & verdict ...",
        "returnDisplay": "... first 500 chars of the above ...",
        "errorMessages": [... console errors ...],
        "messages": [... conversation with any <image> tags scrubbed ...]
    }
    ```
    """

    Name = "frontend_test"

    # ------------------------------------------------------------------ #
    # Construction                                                       #
    # ------------------------------------------------------------------ #
    def __init__(self, working_dir: str, log_dir: str):
        self.base_log_dir = log_dir
        os.makedirs(self.base_log_dir, exist_ok=True)

        super().__init__(
            self.Name,
"""
Launches your website dev server and drives it with a multimodal GUI agent to perform a realistic, browser-level task.

When to use
- **After implementing a new front-end feature** to verify that the feature works from the user's perspective.  
- **At the end of website development** for a full end-to-end validation of the completed UI.

What it does
1. Kills anything already bound to `required_ports` to avoid “address in use”.
2. Starts the dev server via `start_command` in `directory_path`.
3. Opens a Chromium instance on the landing page of the website and follows the given natural-language `instruction` step-by-step until:
    - the agent decides the goal is achieved, **or**  
    - an uncaught runtime error appears in the browser console or server terminal.
5. Returns a summary of the testing process containing GUI agent trajectory development, errors and their triggering actions, a GUI agent testing score (1-5, the higher the better), webpage appearance descriptions, and an appearance grade (1-5, the higher the better).

Expectation for required parameters
1. `directory_path` MUST be an **absolute** path that already exists; the dev server is launched here.
2. `start_command` MUST be the **exact shell command** that starts the dev server (e.g. `npm run dev`).
  - Do not:
    - append & or use other ways of sending the process to the background;
    - chain several unrelated commands with &&, ;, or |.
  - You should:
    - Pass a single, foreground command.
    - Often, the command to start both frontend and backend has already been provided by the project. Use that.
    - If you need to start multiple services, wrap them in a separate script or use a tool like concurrently, then reference that script/tool here.
3. `required_ports` MUST list **every port** the dev server will bind to; any existing listeners on these ports are killed before start.  
4. `instruction` MUST be a clear **natural-language instruction** describing the task the GUI agent should complete.

IMPORTANT: If there is a backend as well, you must start the backend togther with the frontend. In particular:
    - `directory_path` should be the root directory containing both frontend and backend.
    - `start_command` should start both the backend and the frontend.
    - `required_ports` should contain both the backend and the frontend ports.
If you fail to start the backend, the frontend would be unable to connect to it and errors would occur.
""".strip(),
            {
                "type": "object",
                "properties": {
                    "directory_path": {
                        "type": "string",
                        "description": "Absolute path where start_command is executed.",
                    },
                    "start_command": {
                        "type": "string",
                        "description": "Shell command to start the dev server (e.g. `npm run dev`).",
                    },
                    "required_ports": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "All TCP ports the service binds to.",
                    },
                    "instruction": {
                        "type": "string",
                        "description": "Natural-language instruction for the web agent.",
                    },
                },
                "required": [
                    "directory_path",
                    "start_command",
                    "required_ports",
                    "instruction",
                ],
            },
            ToolKind.EXECUTE,
        )
        self.working_dir = working_dir

    # ------------------------------------------------------------------ #
    # Validation                                                         #
    # ------------------------------------------------------------------ #
    def validate_params(self, params: Dict[str, Any]) -> Optional[str]:
        err = super().validate_params(params)
        if err:
            return err

        if not os.path.isabs(params["directory_path"]):
            return "directory_path must be absolute"

        if not os.path.exists(params["directory_path"]):
            return f"directory_path does not exist: {params['directory_path']}"

        if not isinstance(params["required_ports"], list) or not all(
            isinstance(p, (int, float)) for p in params["required_ports"]
        ):
            return "`required_ports` must be an array of numbers"

        return None

    # ------------------------------------------------------------------ #
    # Execution                                                          #
    # ------------------------------------------------------------------ #
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        val_err = self.validate_params(params)
        if val_err:
            return {
                "llmContent": f"Error: {val_err}",
                "returnDisplay": f"Error: {val_err}",
                "error": {"type": "invalid_tool_params", "message": val_err},
            }

        # 1. Free requested ports
        for p in params["required_ports"]:
            kill_service_on_port(int(p))

        # 2. Determine run-specific log directory
        idx = _next_index(self.base_log_dir)
        run_log_dir = os.path.join(self.base_log_dir, f"frontend_test_{idx}")
        os.makedirs(run_log_dir, exist_ok=True)

        # 4. Instantiate tester (constants for optional knobs)
        tester = WebAgentTester(
            directory_path=params["directory_path"],
            start_command=params["start_command"],
            required_ports=[int(p) for p in params["required_ports"]],
            relative_url="",
            instruction=params["instruction"],
            expected_result="",          # not used in this setup
            log_dir=run_log_dir,
            model=os.environ["VLM_MODEL"],
            max_img_num=15,
            max_iterations=20,
            width=1600,
            height=1200,
        )

        # 5. Run test – WebAgentTester already returns the object we need
        t0 = time.time()
        result_obj: Dict[str, Any]
        try:
            result_obj = tester.run_test()  # type: ignore[assignment]
        except Exception as exc:  # noqa: BLE001
            err_msg = f"Tester crashed: {exc}"
            return {
                "llmContent": err_msg,
                "returnDisplay": err_msg,
                "error": {"type": "runtime_exception", "message": err_msg},
            }

        result_obj.setdefault("duration_sec", round(time.time() - t0, 2))
        return result_obj