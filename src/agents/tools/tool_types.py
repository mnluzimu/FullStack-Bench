"""
Tool types and enums for Qwen Code Python.
"""
from enum import Enum
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass


class ToolKind(Enum):
    """Categories of tools for better organization and permissions."""
    READ = "read"
    EDIT = "edit"
    DELETE = "delete"
    MOVE = "move"
    SEARCH = "search"
    EXECUTE = "execute"
    THINK = "think"
    FETCH = "fetch"
    OTHER = "other"


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


@dataclass
class ToolLocation:
    """Represents a file system location that a tool will affect."""
    path: str
    line: Optional[int] = None


@dataclass
class ToolResult:
    """Result of a tool execution."""
    llmContent: Union[str, List[Dict[str, Any]]]
    returnDisplay: Union[str, Dict[str, Any]]
    error: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None


@dataclass
class ToolConfirmationDetails:
    """Details for tool execution confirmation."""
    type: str  # 'edit', 'exec', 'info'
    title: str
    onConfirm: callable
    # For edit type
    fileName: Optional[str] = None
    filePath: Optional[str] = None
    fileDiff: Optional[str] = None
    originalContent: Optional[str] = None
    newContent: Optional[str] = None
    # For exec type
    command: Optional[str] = None
    rootCommand: Optional[str] = None
    # For info type
    prompt: Optional[str] = None
    urls: Optional[List[str]] = None


class ToolConfirmationOutcome(Enum):
    """Outcomes for tool confirmation."""
    PROCEED_ONCE = "proceed_once"
    PROCEED_ALWAYS = "proceed_always"
    CANCEL = "cancel"