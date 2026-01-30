"""
Enhanced error handling utilities for Qwen Code Python implementation with detailed error types.
"""
from typing import Dict, Any, Optional
from enum import Enum

class ToolErrorType(Enum):
    """Specific error types for better error handling."""
    FILE_NOT_FOUND = "file_not_found"
    INVALID_TOOL_PARAMS = "invalid_tool_params"
    FILE_TOO_LARGE = "file_too_large"
    READ_CONTENT_FAILURE = "read_content_failure"
    FILE_WRITE_FAILURE = "file_write_failure"
    PERMISSION_DENIED = "permission_denied"
    NO_SPACE_LEFT = "no_space_left"
    TARGET_IS_DIRECTORY = "target_is_directory"
    ATTEMPT_TO_CREATE_EXISTING_FILE = "attempt_to_create_existing_file"
    EDIT_NO_OCCURRENCE_FOUND = "edit_no_occurrence_found"
    EDIT_EXPECTED_OCCURRENCE_MISMATCH = "edit_expected_occurrence_mismatch"
    EDIT_NO_CHANGE = "edit_no_change"
    EDIT_PREPARATION_FAILURE = "edit_preparation_failure"
    UNHANDLED_EXCEPTION = "unhandled_exception"


class ToolError(Exception):
    """Base exception for tool-related errors."""
    
    def __init__(self, message: str, error_type: ToolErrorType = ToolErrorType.UNHANDLED_EXCEPTION):
        super().__init__(message)
        self.error_type = error_type


class ToolNotFoundError(ToolError):
    """Exception raised when a tool is not found."""
    
    def __init__(self, tool_name: str):
        super().__init__(f"Tool not found: {tool_name}", ToolErrorType.INVALID_TOOL_PARAMS)


class ToolExecutionError(ToolError):
    """Exception raised when a tool execution fails."""
    
    def __init__(self, tool_name: str, message: str, error_type: ToolErrorType = ToolErrorType.UNHANDLED_EXCEPTION):
        super().__init__(f"Error executing tool {tool_name}: {message}", error_type)


def format_tool_error(error: Exception) -> Dict[str, Any]:
    """Format a tool error for display."""
    if isinstance(error, ToolError):
        return {
            "error": str(error),
            "error_type": error.error_type.value if isinstance(error.error_type, ToolErrorType) else str(error.error_type)
        }
    else:
        return {
            "error": str(error),
            "error_type": "unhandled_exception"
        }