"""
Enhanced edit tool for Qwen Code Python implementation with support for expected replacements, better error handling, and tool kinds.
"""
import os
import difflib
from typing import Dict, Any
from .base_tool import BaseTool
from .tool_types import ToolKind, ToolErrorType


def apply_replacement(current_content: str, old_string: str, new_string: str) -> str:
    """Apply replacement to content."""
    if old_string == "":
        return new_string
    return current_content.replace(old_string, new_string)


class EditTool(BaseTool):
    """Enhanced tool for replacing text within files with support for expected replacements."""
    Name = "replace"
    
    def __init__(self, working_dir: str):
        super().__init__(
            self.Name,
            """Replaces text within a file. By default, replaces a single occurrence, but can replace multiple occurrences when `expected_replacements` is specified. This tool requires providing significant context around the change to ensure precise targeting. Always use the read_file tool to examine the file's current content before attempting a text replacement.

The user has the ability to modify the `new_string` content. If modified, this will be stated in the response.

Expectation for required parameters:
1. `file_path` MUST be an absolute path; otherwise an error will be thrown.
2. `old_string` MUST be the exact literal text to replace (including all whitespace, indentation, newlines, and surrounding code etc.).
3. `new_string` MUST be the exact literal text to replace `old_string` with (also including all whitespace, indentation, newlines, and surrounding code etc.). Ensure the resulting code is correct and idiomatic.
4. NEVER escape `old_string` or `new_string`, that would break the exact literal text requirement.
**Important:** If ANY of the above are not satisfied, the tool will fail. CRITICAL for `old_string`: Must uniquely identify the single instance to change. Include at least 3 lines of context BEFORE and AFTER the target text, matching whitespace and indentation precisely. If this string matches multiple locations, or does not match exactly, the tool will fail.
**Multiple replacements:** Set `expected_replacements` to the number of occurrences you want to replace. The tool will replace ALL occurrences that match `old_string` exactly. Ensure the number of replacements matches your expectation.""",
            {
                "type": "object",
                "properties": {
                    "path": {
                        "description": "The absolute path to the file to modify. Must start with '/'.",
                        "type": "string",
                    },
                    "old_string": {
                        "description": "The exact literal text to replace, preferably unescaped. For single replacements (default), include at least 3 lines of context BEFORE and AFTER the target text, matching whitespace and indentation precisely. For multiple replacements, specify expected_replacements parameter. If this string is not the exact literal text (i.e. you escaped it) or does not match exactly, the tool will fail.",
                        "type": "string",
                    },
                    "new_string": {
                        "description": "The exact literal text to replace `old_string` with, preferably unescaped. Provide the EXACT text. Ensure the resulting code is correct and idiomatic.",
                        "type": "string",
                    },
                    "expected_replacements": {
                        "type": "number",
                        "description": "Number of replacements expected. Defaults to 1 if not specified. Use when you want to replace multiple occurrences.",
                        "minimum": 1,
                    },
                },
                "required": ["path", "old_string", "new_string"],
            },
            ToolKind.EDIT
        )
        self.working_dir = working_dir
        
    def validate_params(self, params: Dict[str, Any]) -> str:
        error = super().validate_params(params)
        if error:
            return error
            
        file_path = params["path"]
        if not os.path.isabs(file_path):
            return f"File path must be absolute: {file_path}"
            
        # Check if path is within working directory
        try:
            relative_path = os.path.relpath(file_path, self.working_dir)
            if relative_path.startswith(".."):
                return f"File path must be within the working directory ({self.working_dir}): {file_path}"
        except ValueError:
            return f"Invalid file path: {file_path}"
            
        return None
        
    def get_description(self, params: Dict[str, Any]) -> str:
        """Get a description of the edit operation."""
        if not params.get("path"):
            return "Model did not provide valid parameters for edit tool, missing or empty \"file_path\""
            
        file_path = params["path"]
        old_string = params.get("old_string", "")
        new_string = params.get("new_string", "")
        
        try:
            relative_path = os.path.relpath(file_path, self.working_dir)
        except ValueError:
            relative_path = file_path
            
        # Shorten path for display
        path_parts = relative_path.split(os.sep)
        if len(path_parts) > 3:
            shortened = os.sep.join(["..."] + path_parts[-3:])
        else:
            shortened = relative_path
            
        if old_string == "":
            return f"Create {shortened}"
            
        old_string_snippet = old_string.split("\n")[0][:30] + ("..." if len(old_string) > 30 else "")
        new_string_snippet = new_string.split("\n")[0][:30] + ("..." if len(new_string) > 30 else "")
        
        if old_string == new_string:
            return f"No file changes to {shortened}"
            
        return f"{shortened}: {old_string_snippet} => {new_string_snippet}"
        
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        error = self.validate_params(params)
        if error:
            return {
                "llmContent": f"Error: Invalid parameters provided. Reason: {error}",
                "returnDisplay": f"Error: {error}",
                "error": {
                    "message": error,
                    "type": "invalid_tool_params"
                }
            }
            
        file_path = params["path"]
        old_string = params["old_string"]
        new_string = params["new_string"]
        expected_replacements = params.get("expected_replacements", 1)
        modified_by_user = params.get("modified_by_user", False)
        ai_proposed_string = params.get("ai_proposed_string", new_string)
        
        try:
            # Check if file exists
            file_exists = os.path.exists(file_path)
            
            # Read current content
            if file_exists:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        current_content = f.read()
                        # Normalize line endings to LF for consistent processing
                        current_content = current_content.replace("\r\n", "\n")
                except PermissionError:
                    return {
                        "llmContent": f"Error: Permission denied reading file: {file_path}",
                        "returnDisplay": "Error: Permission denied reading file.",
                        "error": {
                            "message": f"Permission denied reading file: {file_path}",
                            "type": "permission_denied"
                        }
                    }
                except Exception as e:
                    return {
                        "llmContent": f"Error: Failed to read existing file: {file_path}. {str(e)}",
                        "returnDisplay": f"Error: Failed to read existing file: {str(e)}",
                        "error": {
                            "message": f"Failed to read existing file: {file_path}. {str(e)}",
                            "type": "read_content_failure"
                        }
                    }
            else:
                if old_string != "":
                    return {
                        "llmContent": "Could not read file because no file was found at the specified path.",
                        "returnDisplay": "Error: File not found. Cannot apply edit. Use an empty old_string to create a new file.",
                        "error": {
                            "message": f"File not found: {file_path}",
                            "type": "file_not_found"
                        }
                    }
                current_content = ""
            
            # Apply replacement logic
            is_new_file = (old_string == "" and not file_exists)
            
            if is_new_file:
                # Creating a new file
                new_content = new_string
                occurrences = 1
            else:
                # Editing existing file
                if old_string == "" and file_exists:
                    return {
                        "llmContent": f"Failed to edit. Attempted to create a file that already exists.",
                        "returnDisplay": "Error: Failed to edit. Attempted to create a file that already exists.",
                        "error": {
                            "message": f"File already exists, cannot create: {file_path}",
                            "type": "attempt_to_create_existing_file"
                        }
                    }
                    
                # Count occurrences
                occurrences = current_content.count(old_string)
                
                if occurrences == 0:
                    return {
                        "llmContent": f"Failed to edit, could not find the string to replace.",
                        "returnDisplay": "Error: Failed to edit, could not find the string to replace.",
                        "error": {
                            "message": f"Failed to edit, 0 occurrences found for old_string in {file_path}. No edits made. The exact text in old_string was not found. Ensure you're not escaping content incorrectly and check whitespace, indentation, and context. Use read_file tool to verify.",
                            "type": "edit_no_occurrence_found"
                        }
                    }
                    
                if occurrences != expected_replacements:
                    occurrence_term = "occurrence" if expected_replacements == 1 else "occurrences"
                    return {
                        "llmContent": f"Failed to edit, expected {expected_replacements} {occurrence_term} but found {occurrences}.",
                        "returnDisplay": f"Error: Failed to edit, expected {expected_replacements} {occurrence_term} but found {occurrences}.",
                        "error": {
                            "message": f"Failed to edit, Expected {expected_replacements} {occurrence_term} but found {occurrences} for old_string in file: {file_path}",
                            "type": "edit_expected_occurrence_mismatch"
                        }
                    }
                
                # Check if there are actually changes
                if old_string == new_string:
                    return {
                        "llmContent": f"No changes to apply. The old_string and new_string are identical.",
                        "returnDisplay": "No changes to apply. The old_string and new_string are identical.",
                        "error": {
                            "message": f"No changes to apply. The old_string and new_string are identical in file: {file_path}",
                            "type": "edit_no_change"
                        }
                    }
                
                # Perform the replacement
                new_content = apply_replacement(current_content, old_string, new_string)
            
            # Create parent directories if needed
            try:
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
            except PermissionError:
                return {
                    "llmContent": f"Error: Permission denied creating directory for file: {file_path}",
                    "returnDisplay": "Error: Permission denied creating directory.",
                    "error": {
                        "message": f"Permission denied creating directory for file: {file_path}",
                        "type": "permission_denied"
                    }
                }
            
            # Write the new content to the file
            try:
                with open(file_path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(new_content)
            except PermissionError:
                return {
                    "llmContent": f"Error: Permission denied writing to file: {file_path} (EACCES)",
                    "returnDisplay": "Error: Permission denied writing to file.",
                    "error": {
                        "message": f"Permission denied writing to file: {file_path} (EACCES)",
                        "type": "permission_denied"
                    }
                }
            except OSError as e:
                if e.errno == 28:  # No space left on device
                    return {
                        "llmContent": f"Error: No space left on device: {file_path} (ENOSPC)",
                        "returnDisplay": "Error: No space left on device.",
                        "error": {
                            "message": f"No space left on device: {file_path} (ENOSPC)",
                            "type": "no_space_left"
                        }
                    }
                elif e.errno == 21:  # Is a directory
                    return {
                        "llmContent": f"Error: Target is a directory, not a file: {file_path} (EISDIR)",
                        "returnDisplay": "Error: Target is a directory, not a file.",
                        "error": {
                            "message": f"Target is a directory, not a file: {file_path} (EISDIR)",
                            "type": "target_is_directory"
                        }
                    }
                else:
                    return {
                        "llmContent": f"Error: Failed to write file '{file_path}': {str(e)} ({getattr(e, 'errno', 'unknown')})",
                        "returnDisplay": f"Error: Failed to write file: {str(e)}",
                        "error": {
                            "message": f"Failed to write file '{file_path}': {str(e)} ({getattr(e, 'errno', 'unknown')})",
                            "type": "file_write_failure"
                        }
                    }
            
            # Generate diff for display
            diff = "\n".join(difflib.unified_diff(
                (current_content or "").splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile="Current",
                tofile="Proposed",
                lineterm=""
            ))
            
            # Prepare result
            if is_new_file:
                display_result = f"Created {os.path.relpath(file_path, self.working_dir)}"
                llm_success_message_parts = [f"Created new file: {file_path} with provided content."]
            else:
                display_result = {
                    "fileDiff": diff,
                    "fileName": os.path.basename(file_path),
                    "originalContent": current_content,
                    "newContent": new_content
                }
                llm_success_message_parts = [f"Successfully modified file: {file_path} ({occurrences} replacements)."]
                
            if modified_by_user:
                llm_success_message_parts.append(f"User modified the `new_string` content to be: {new_string}.")
            
            return {
                "llmContent": " ".join(llm_success_message_parts),
                "returnDisplay": display_result,
            }
            
        except Exception as e:
            return {
                "llmContent": f"Error executing edit: {str(e)}",
                "returnDisplay": f"Error: {str(e)}",
                "error": {
                    "message": str(e),
                    "type": "edit_preparation_failure"
                }
            }
