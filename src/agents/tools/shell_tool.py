"""
Enhanced shell command tool for Qwen Code Python implementation with better process management and security features.
"""
import os
import sys
import subprocess
import tempfile
import shlex
from typing import Dict, Any, List
from .base_tool import BaseTool
from .tool_types import ToolKind

# Import terminal module
from terminal import BashSession, CmdRunAction


def get_command_roots(command: str) -> List[str]:
    """Extracts the root commands from a given shell command string."""
    if not command:
        return []
        
    # Remove leading and trailing whitespace
    command = command.strip()
    
    # Handle command chaining and grouping
    # Split on command separators but be careful with quotes and grouping
    roots = []
    
    # Simple approach: split on common separators and extract first word of each part
    parts = []
    current_part = ""
    in_quote = None
    i = 0
    
    while i < len(command):
        char = command[i]
        
        if char in ['"', "'"] and (i == 0 or command[i-1] != '\\\\'):
            if in_quote == char:
                in_quote = None
            elif in_quote is None:
                in_quote = char
        elif char in [';', '&', '|'] and in_quote is None:
            if current_part.strip():
                parts.append(current_part.strip())
            current_part = ""
        else:
            current_part += char
        i += 1
        
    if current_part.strip():
        parts.append(current_part.strip())
    
    # Extract root command from each part
    for part in parts:
        # Remove grouping operators
        part = part.replace("{", "").replace("}", "").replace("(", "").replace(")", "")
        
        # Handle background processes
        part = part.rstrip("&").strip()
        
        # Split on whitespace and take first part
        sub_parts = part.split()
        if sub_parts:
            # Take first part and split on path separators
            root_part = sub_parts[0]
            path_parts = [p for p in root_part.split("/") if p]  # Remove empty parts
            
            # Take last part as command root
            if path_parts:
                roots.append(path_parts[-1])
    
    # Remove duplicates while preserving order
    seen = set()
    unique_roots = []
    for root in roots:
        if root not in seen:
            seen.add(root)
            unique_roots.append(root)
            
    return unique_roots


def strip_shell_wrapper(command: str) -> str:
    """Strips shell wrapper commands like bash -c."""
    if not command:
        return command
        
    command = command.strip()
    
    # Handle bash -c wrapper
    if command.startswith("bash -c "):
        # Extract the quoted part
        rest = command[8:].strip()
        if (rest.startswith('"') and rest.endswith('"')) or (rest.startswith("'") and rest.endswith("'")):
            return rest[1:-1]
        return rest
        
    # Handle sh -c wrapper
    if command.startswith("sh -c "):
        # Extract the quoted part
        rest = command[6:].strip()
        if (rest.startswith('"') and rest.endswith('"')) or (rest.startswith("'") and rest.endswith("'")):
            return rest[1:-1]
        return rest
        
    return command


def is_command_allowed(command: str, whitelist: set) -> Dict[str, Any]:
    """Checks if a command is allowed based on whitelist."""
    if not command:
        return {"allowed": False, "reason": "Command is empty"}
        
    roots = get_command_roots(command)
    if not roots:
        return {"allowed": False, "reason": "Could not identify command root to obtain permission from user"}
        
    commands_to_confirm = [root for root in roots if root not in whitelist]
    
    if commands_to_confirm:
        return {"allowed": False, "reason": f"Command(s) require confirmation: {', '.join(commands_to_confirm)}"}
        
    return {"allowed": True}


class ShellTool(BaseTool):
    """Enhanced tool for executing shell commands with better security and process management."""
    Name = "run_shell_command"
    
    def __init__(self, working_dir: str):
        super().__init__(
            self.Name,
            """Execute a bash command in the terminal.

Long running commands: For commands that may run indefinitely, it should be run in the background and the output should be redirected to a file, e.g. command = `python3 app.py > server.log 2>&1 &`.

Interact with running process: If a bash command returns exit code `-1`, this means the process is not yet finished. By setting `is_input` to `true`, the assistant can interact with the running process and send empty `command` to retrieve any additional logs, or send additional text (set `command` to the text) to STDIN of the running process, or send command like `C-c` (Ctrl+C) to interrupt the process.

One command at a time: You can only execute one bash command at a time. If you need to run multiple commands sequentially, you can use `&&` or `;` to chain them together.

The following information is returned:

Command: Executed command.
Directory: current working directory after the command has been executed.
Stdout: Output of the command. Can be `(empty)` on error or when no output exists and for any unwaited background processes.
Exit Code: Exit code or `(none)` if terminated by signal.""",
            {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The bash command to execute. Can be empty string to view additional logs when previous exit code is `-1`. Can be `C-c` (Ctrl+C) to interrupt the currently running process. Note: You can only execute one bash command at a time. If you need to run multiple commands sequentially, you can use `&&` or `;` to chain them together."
                    },
                    "is_input": {
                        "type": "boolean",
                        "description": "If True, the command is an input to the running process. If False, the command is a bash command to be executed in the terminal."
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of the command for the user. Be specific and concise. Ideally a single sentence. Can be up to 3 sentences for clarity. No line breaks."
                    },
                },
                "required": ["command"]
            },
            ToolKind.EXECUTE
        )
        self.working_dir = working_dir
        # Initialize a persistent BashSession
        self.bash_session = BashSession(working_dir, "root")
        
    def __del__(self):
        """Clean up the bash session when the object is destroyed."""
        if hasattr(self, 'bash_session') and self.bash_session:
            self.bash_session.close()
            
    def __enter__(self):
        """Context manager entry."""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close the bash session."""
        if hasattr(self, 'bash_session') and self.bash_session:
            self.bash_session.close()
        return False  # Don't suppress exceptions
        
    def validate_params(self, params: Dict[str, Any]) -> str:
        error = super().validate_params(params)
        if error:
            return error
            
        command = params["command"]
        # Command can be empty when is_input is True (for interacting with running processes)
        if not command.strip() and not params.get("is_input", False):
            return "Command cannot be empty."
                
        return None
        
    def get_description(self, params: Dict[str, Any]) -> str:
        """Get a description of the command being executed."""
        command = params.get("command", "")
        is_input = params.get("is_input", False)
        description = params.get("description", "")
        
        stripped_command = strip_shell_wrapper(command)
        root_commands = get_command_roots(stripped_command)
        
        result = stripped_command
        if is_input:
            result += " [input]"
        # append optional (description), replacing any line breaks with spaces
        if description:
            result += f" ({description.replace(chr(10), ' ')})"  # Replace newlines with spaces
            
        return result
        
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        error = self.validate_params(params)
        if error:
            return {
                "llmContent": f"Command rejected: {params.get('command', '')}\nReason: {error}",
                "returnDisplay": f"Error: {error}"
            }
            
        command = params["command"]
        is_input = params.get("is_input", False)
        
        # Strip shell wrapper
        stripped_command = strip_shell_wrapper(command)
        
        try:
            action = CmdRunAction(
                command=stripped_command,
                is_input=is_input,
                blocking=True,
                timeout=None
            )
            result = self.bash_session.execute(action)
            
            output = f"Command: {stripped_command}\n"
            output += f"Directory: {result.metadata.working_dir}\n"
            output += f"Stdout: {result.content or '(empty)'}\n"
            output += f"Exit Code: {result.metadata.exit_code}"

            return_display = output
            
            return {
                "llmContent": output,
                "returnDisplay": return_display
            }
            
        except PermissionError:
            return {
                "llmContent": f"Error: Permission denied executing command: {stripped_command}",
                "returnDisplay": "Error: Permission denied executing command."
            }
        except FileNotFoundError:
            return {
                "llmContent": f"Error: Command not found: {stripped_command}",
                "returnDisplay": "Error: Command not found."
            }
        except Exception as e:
            return {
                "llmContent": f"Error executing command: {str(e)}",
                "returnDisplay": f"Error: {str(e)}"
            }