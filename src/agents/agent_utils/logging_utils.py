"""
Logging utilities for Qwen Code Python implementation.
"""
import os
import json
from typing import Dict, Any, Optional, List
from datetime import datetime


class SessionLogger:
    """Logger for session data."""
    
    def __init__(self, log_dir):
        self.log_dir = log_dir
        self.log_file = os.path.join(self.log_dir, "session.log")
        self.session_name = os.path.basename(self.log_dir)
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir, exist_ok=True)
        
    def log_llm_request_response(self, 
        step: int, 
        tag: str, 
        request: Dict[str, Any], 
        response: Optional[Dict[str, Any]] = None, 
        error: Optional[str] = None, 
        tool_call_history:List[Dict[str, Any]] = None, 
        chosen_template_name: Optional[str] = None,
        is_frontend: bool = None
    ):
        """Log an LLM request and response."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "step": step,
            "tag": tag,
            "type": "llm_request_response",
            "request": request,
            "response": response,
            "error": error,
            "tool_call_history": tool_call_history,
            "chosen_template_name": chosen_template_name
        }
        self._write_log(step, tag, log_entry, is_frontend)
        self.log_message(f"step {step} {tag} saved; history length: {len(request['messages'])}; error: {error}")

    def log_message(self, message: str, is_frontend: bool = None):
        if is_frontend is None:
            tag = ""
        else:
            tag = "[frontend]" if is_frontend else "[backend]"
        log_message = f"[{datetime.now().isoformat()}][{self.session_name}]{tag} {message}"
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(log_message + "\n")
        print(log_message)
        
    def _write_log(self, step: int, tag: str, log_entry: Dict[str, Any], is_frontend: bool = None):
        """Write a log entry to file."""
        if is_frontend is not None:
            sub_dir = "frontend" if is_frontend else "backend"
            log_dir = os.path.join(self.log_dir, sub_dir)
            if not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
        else:
            log_dir = self.log_dir
        log_file = os.path.join(log_dir, f"{step}_{tag}.json")
        try:
            with open(log_file, "w", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False, indent=4) + "\n")
        except Exception:
            # Silently ignore logging errors
            pass