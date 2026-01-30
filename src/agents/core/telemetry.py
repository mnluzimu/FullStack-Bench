"""
Telemetry module for Qwen Code Python implementation.
"""
import os
import json
import uuid
from typing import Dict, Any, Optional
from datetime import datetime


class TelemetryLogger:
    """Logger for telemetry data."""
    
    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self.session_id = str(uuid.uuid4())
        self.logs_dir = os.path.join(project_dir, ".qwen", "logs")
        os.makedirs(self.logs_dir, exist_ok=True)
        
    def log_user_prompt(self, prompt: str, prompt_id: str, auth_type: Optional[str] = None):
        """Log a user prompt."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "event_type": "user_prompt",
            "prompt_id": prompt_id,
            "prompt": prompt,
            "auth_type": auth_type
        }
        self._write_log(log_entry)
        
    def log_llm_request_response(self, request: Dict[str, Any], response: Optional[Dict[str, Any]] = None, error: Optional[str] = None):
        """Log an LLM request and response."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "event_type": "llm_request_response",
            "request": request,
            "response": response,
            "error": error
        }
        self._write_log(log_entry)
        
    def log_tool_execution(self, tool_name: str, params: Dict[str, Any], result: Dict[str, Any], error: Optional[str] = None):
        """Log a tool execution."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "event_type": "tool_execution",
            "tool_name": tool_name,
            "params": params,
            "result": result,
            "error": error
        }
        self._write_log(log_entry)
        
    def _write_log(self, log_entry: Dict[str, Any]):
        """Write a log entry to file."""
        log_file = os.path.join(self.logs_dir, f"telemetry_{datetime.now().strftime('%Y-%m-%d')}.json")
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception:
            # Silently ignore logging errors
            pass


# Global telemetry logger instance
_telemetry_logger: Optional[TelemetryLogger] = None


def initialize_telemetry(project_dir: str):
    """Initialize telemetry logging."""
    global _telemetry_logger
    _telemetry_logger = TelemetryLogger(project_dir)


def get_telemetry_logger() -> Optional[TelemetryLogger]:
    """Get the telemetry logger instance."""
    return _telemetry_logger