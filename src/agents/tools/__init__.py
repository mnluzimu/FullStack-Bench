from .base_tool import BaseTool
from .file_tools import ReadFileTool, WriteFileTool, ListDirectoryTool, GlobTool
from .grep_tool import GrepTool
from .read_many_files_tool import ReadManyFilesTool
from .backend_test_tool import BackendTestTool
from .tool_types import ToolKind, ToolConfirmationDetails


def get_info_gathering_tools(working_dir: str, log_dir: str = None):
    """Get info gathering tools."""
    return [
        ReadFileTool(working_dir),
        ListDirectoryTool(working_dir),
        GlobTool(working_dir),
        GrepTool(working_dir),
        ReadManyFilesTool(working_dir),
    ]


def get_backend_testing_tools(working_dir: str, log_dir: str = None):
    """Get info gathering tools."""
    return [
        ReadFileTool(working_dir),
        ListDirectoryTool(working_dir),
        GlobTool(working_dir),
        GrepTool(working_dir),
        ReadManyFilesTool(working_dir),
        BackendTestTool(working_dir, log_dir)
    ]