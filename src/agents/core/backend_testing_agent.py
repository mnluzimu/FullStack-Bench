"""
Core module for Qwen Code Python implementation.
"""
import os
import json
import sys
import glob
from typing import List, Dict, Any
from tqdm import tqdm
from dataclasses import dataclass
import re
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_utils import SessionLogger, llm_generation
from tools import get_backend_testing_tools
from .system_prompt import (
    get_compression_prompt, 
    get_backend_testing_prompt,
    get_backend_judging_prompt,
    get_db_actions_judging_prompt
)
from .tool_registry import ToolRegistry
from .compress_output import compress_output

from utils import DBWatcher

@dataclass
class BackendTestingAgentConfig:
    task: str
    expected_result: str
    info_path: str
    model: str
    working_dir: str
    log_dir: str
    db_dir: str
    max_history_length: int = 20
    max_iterations: int = 50
    overwrite: bool = False
    max_tokens: int = 8192
    compression_ratio: float = 0.5
    db_exists:  bool = True


class BackendTestingAgent:
    """The info gathering agent."""
    
    def __init__(self, config: BackendTestingAgentConfig):
        self.config = config
        self.llm_generation = llm_generation

        if not os.path.isfile(config.info_path):
            raise ValueError(f"Info path {config.info_path} does not exist!")

        with open(config.info_path, "r", encoding="utf-8") as f:
            info_data = json.load(f)
        self.history = info_data["history"]
        user_prompt = get_backend_testing_prompt(self.config.task, self.config.expected_result)
        self.history.append({"role": "user", "content": user_prompt})

        self.tool_call_history: List[Dict[str, Any]] = []  # New attribute to track all tool calls
        self.max_history_length = self.config.max_history_length
        # Create a new session logger for this agent instance
        self.session_logger = SessionLogger(self.config.log_dir)
        if self.config.db_exists and os.path.isdir(self.config.db_dir):
            self.db_watcher = DBWatcher(self.config.db_dir)
        else:
            self.db_watcher = None

        self.initialize_tool_registry()

    def initialize_tool_registry(self):
        self.tools = get_backend_testing_tools(self.config.working_dir, self.config.log_dir)
        self.registry = ToolRegistry()
        for tool in self.tools:
            self.registry.register_tool(tool)

    def initialize_agent(self) -> int:
        """Initialize the client with system context. If previous logs exist, restart from the last step."""
        # Check if we should restart from a previous run
        log_dir = self.config.log_dir
        start_step = 0
        if not self.config.overwrite and os.path.exists(log_dir):
            # Look for existing tool response files to determine the last completed step
            tool_response_files = glob.glob(os.path.join(log_dir, "*_tool_response.json"))
            if tool_response_files:
                # Extract step numbers and sort them in descending order
                step_numbers = []
                for file_path in tool_response_files:
                    filename = os.path.basename(file_path)
                    try:
                        step_num = int(filename.split("_")[0])
                        step_numbers.append(step_num)
                    except ValueError:
                        continue
                
                if step_numbers:
                    step_numbers.sort(reverse=True)  # Sort in descending order
                    
                    # Try to load history from the most recent logs, going backwards until one succeeds
                    for step_num in step_numbers:
                        self.session_logger.log_message(f"Attempting to restart from step {step_num}")
                        log_file = os.path.join(log_dir, f"{step_num}_tool_response.json")
                        try:
                            with open(log_file, "r", encoding="utf-8") as f:
                                log_data = json.load(f)
                                # Restore history from the logged messages
                                if "request" in log_data and "messages" in log_data["request"]:
                                    # Start with the base messages from the request
                                    self.history = log_data["request"]["messages"] + log_data.get("response", [])

                                    # Load tool_call_history if it exists
                                    if "tool_call_history" in log_data:
                                        self.tool_call_history = log_data["tool_call_history"]
                                        # Execute tool calls that would affect the environment state
                                        self._restore_environment_state()

                                    start_step = step_num + 1  # Next step should be one more than the loaded step
                                    self.session_logger.log_message(f"Loaded history with {len(self.history)} messages from step {step_num}")
                                    self.session_logger.log_message(f"Restarting from step {start_step}")
                                    break  # Successfully loaded, exit the loop
                        except (json.JSONDecodeError, FileNotFoundError, KeyError) as e:
                            # Log the error and continue to the next log file
                            self.session_logger.log_message(f"Failed to load log file {log_file}: {str(e)}")
                            continue
                    else:
                        # If we get here, all log loading attempts failed
                        self.session_logger.log_message("Failed to load any previous logs, starting from scratch")
        
        return start_step

    def _restore_environment_state(self):
        """Execute tool calls that would affect the environment state to restore it."""
        # List of tools that affect the environment state
        state_affecting_tools = {"backend_test",}
        
        self.session_logger.log_message(f"Restoring environment state with {len(self.tool_call_history)} tool calls")
        
        for i, tool_call in enumerate(self.tool_call_history):
            tool_name = tool_call.get("function", {}).get("name")
            if tool_name in state_affecting_tools:
                try:
                    tool_args = json.loads(tool_call["function"]["arguments"])
                    self.session_logger.log_message(f"Executing state-restoring tool call {i}: {tool_name}")
                    # Execute the tool call to restore the environment state
                    self.registry.execute_tool(tool_name, tool_args)
                except Exception as e:
                    self.session_logger.log_message(f"Failed to execute state-restoring tool call {i}: {str(e)}")
                    # Continue with the next tool call even if one fails
                    continue
        
        self.session_logger.log_message("Environment state restoration completed")
        
    def _compress_history(self, force=False, compression_ratio=None):
        if compression_ratio is None:
            compression_ratio = self.config.compression_ratio
        """Compress history using the compression prompt when it exceeds maximum length."""
        if len(self.history) > self.max_history_length or force:
            # Group messages to ensure assistant messages with tool calls and their responses stay together
            grouped_history = []
            i = 3  # Start from index 3 to skip the initial context
            while i < len(self.history):
                # If current message is an assistant message with tool calls
                if (self.history[i].get("role") == "assistant" and 
                    "tool_calls" in self.history[i] and 
                    self.history[i]["tool_calls"]):
                    # Group this assistant message with its tool responses
                    group = [self.history[i]]
                    i += 1
                    # Add all subsequent tool responses
                    while i < len(self.history) and self.history[i].get("role") == "tool":
                        group.append(self.history[i])
                        i += 1
                    grouped_history.append(group)
                else:
                    # Single message group
                    grouped_history.append([self.history[i]])
                    i += 1

            if len(grouped_history) <= self.max_history_length and not force:
                return
            # Split into compressed_history and remaining_history
            compression_threshold = int(len(grouped_history) * compression_ratio)
            if compression_threshold > 0:
                compressed_groups = grouped_history[:-compression_threshold]
                remaining_groups = grouped_history[-compression_threshold:]
            else:
                compressed_groups = grouped_history
                remaining_groups = []

            # Flatten the groups
            compressed_history = []
            for group in compressed_groups:
                compressed_history.extend(group)
                
            remaining_history = []
            for group in remaining_groups:
                remaining_history.extend(group)
            
            # If there's nothing to compress, just trim the history
            if not compressed_history:
                # Keep the initial context and the remaining history
                self.history = self.history[:3] + remaining_history
                return

            try:
                # Prepare the compression prompt with the compressible history
                compression_prompt = get_compression_prompt()
                
                # Create a message to send to the LLM for compression
                compression_messages = [
                    {"role": "system", "content": compression_prompt},
                    {"role": "user", "content": json.dumps(compressed_history)}
                ]
                
                # Send request to LLM to compress the history
                compressed_response = llm_generation(
                    compression_messages, 
                    model=self.config.model,
                    max_tokens=self.config.max_tokens
                )
                
                # Extract the compressed content
                compressed_content = compressed_response.get("content", "")
                
                # Create a compressed history message
                compressed_history_message = {
                    "role": "system",
                    "content": f"<COMPRESSED_HISTORY>{compressed_content}</COMPRESSED_HISTORY>"
                }
                
                # Form the new history: initial context + compressed result + remaining history
                self.history = self.history[:3] + [compressed_history_message] + remaining_history
                
            except Exception as e:
                # If compression fails, fall back to simple trimming
                # Keep initial context and the last N-3 messages
                remaining_groups = grouped_history[- compression_threshold:]
                remaining_history = []
                for group in remaining_groups:
                    remaining_history.extend(group)
                self.history = self.history[:3] + remaining_history
            
    def step(self, step_idx: int) -> Dict[str, Any]:
        """Send a message to the LLM, process the response, update history, and log response."""
        self._compress_history()

        # Prepare request for logging
        request_data = {
            "model": self.config.model,
            "messages": self.history.copy(),
        }
        tool_schemas = self.registry.get_tool_schemas()
        request_data["tool_schemas"] = tool_schemas
            
        try:
            # Send request to LLM
            response = self.llm_generation(self.history, model=self.config.model, tools=tool_schemas, max_tokens=self.config.max_tokens)
            self.session_logger.log_llm_request_response(step_idx, "llm_response", request_data, response)
            self.history.append(response)

            # Execute the tool calls
            request_data = {
                "model": self.config.model,
                "messages": self.history.copy(),
            }
            tool_responses = []
            tool_calls = response.get("tool_calls", None)

            if tool_calls is None or len(tool_calls) == 0:
                content_text = response.get("content", "")
                return {"type": "finished", "summary": content_text}

            for tool_call in tool_calls:
                self.tool_call_history.append(tool_call)
                self.session_logger.log_message(f'executing {tool_call["id"]}: {tool_call["function"]["name"]}...')
                try:
                    tool_args = json.loads(tool_call["function"]["arguments"])
                    tool_result = self.registry.execute_tool(tool_call["function"]["name"], tool_args)
                except json.JSONDecodeError as e:
                    # Handle incomplete or invalid JSON in tool arguments
                    error_msg = f"Invalid JSON in tool arguments: {str(e)}"
                    self.session_logger.log_message(f'error in {tool_call["id"]}: {error_msg}')
                    tool_result = {
                        "llmContent": error_msg,
                        "returnDisplay": error_msg
                    }
                except Exception as e:
                    # Handle other errors in tool execution
                    error_msg = f"Error executing tool: {str(e)}"
                    self.session_logger.log_message(f'error in {tool_call["id"]}: {error_msg}')
                    tool_result = {
                        "llmContent": error_msg,
                        "returnDisplay": error_msg
                    }
                
                return_display = tool_result.get("returnDisplay", "")
                if return_display is None:
                    return_display = ""
                self.session_logger.log_message(f'returned {tool_call["id"]}: {str(return_display)[:500]}')
                content = compress_output(str(tool_result["llmContent"]), self.config.model, tool_call["function"]["name"])
                tool_response = {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": content
                }
                self.history.append(tool_response)
                tool_responses.append(tool_response)
            self.session_logger.log_llm_request_response(step_idx, "tool_response", request_data, tool_responses, tool_call_history=self.tool_call_history)
            
            return {"type": "success"}
                
        except Exception as e:
            # Log error
            self.session_logger.log_llm_request_response(step_idx, "error", request_data, error=str(e))
            self.session_logger.log_message(f"error: {str(e)}")
            if "Please reduce the length of the messages or completion." in str(e):
                self._compress_history(force=True)
            return {"type": "error", "value": str(e)}

    def extract_final_judgement(self, llm_response: str) -> str | None:
        """
        Returns "YES", "NO", or None if the pattern is not found.
        """
        m = re.search(r"Final\s*Judgement:\s*(YES|NO)\b", llm_response, flags=re.IGNORECASE)
        return m.group(1).upper() if m else "NO"

    def extract_db_judgement(self, llm_response: str) -> str | None:
        """
        Returns "YES", "NO", or None if the pattern is not found.
        """
        m = re.search(r"Database\s*Interaction\s*Correctness:\s*(YES|NO)\b", llm_response, flags=re.IGNORECASE)
        return m.group(1).upper() if m else "NO"

    def run_agent(self) -> bool:
        start_step = self.initialize_agent()
        for step_idx in tqdm(range(start_step, self.config.max_iterations)):
            result = self.step(step_idx)
            if result["type"] == "finished":
                return result
        return {"type": "max_iterations_reached"}

    def run(self):
        if self.config.db_exists and self.db_watcher is not None:
            self.db_watcher.set_ckpt()
        time.sleep(15)
        result = self.run_agent()
        time.sleep(15)
        if self.config.db_exists and self.db_watcher is not None:
            new_entries = self.db_watcher.get_new_entries()

        if result["type"] == "finished":
            summary = result.get("summary", "")
            judgement = self.extract_final_judgement(summary)
        else:
            self.history.append({
                "role": "user",
                "content": get_backend_judging_prompt(self.config.task, self.config.expected_result)
            })
            llm_response = llm_generation(self.history, model=self.config.model, max_tokens=self.config.max_tokens)
            self.history.append(llm_response)
            summary = llm_response.get("content", "")
            judgement = self.extract_final_judgement(summary)

        with open(os.path.join(self.config.log_dir, "testing_result.json"), "w", encoding="utf-8") as f:
            json.dump({
                "history": self.history,
                "summary": summary,
                "judgement": judgement
            }, f, indent=4)

        if self.config.db_exists and self.db_watcher is not None:
            self.history.append({
                "role": "user",
                "content": get_db_actions_judging_prompt(new_entries, self.config.task, self.config.expected_result)
            })
            llm_response = llm_generation(self.history, model=self.config.model, max_tokens=self.config.max_tokens)
            self.history.append(llm_response)
            summary = llm_response.get("content", "")
            judgement = self.extract_db_judgement(summary)
            with open(os.path.join(self.config.log_dir, "db_interaction_result.json"), "w", encoding="utf-8") as f:
                json.dump({
                    "history": self.history,
                    "summary": summary,
                    "judgement": judgement
                }, f, indent=4)