"""
Enhanced file-related tools for Qwen Code Python implementation with support for truncation, better error handling, and more features.
"""
import os
import base64
import mimetypes
import fnmatch
from typing import Dict, Any, List, Tuple
from .base_tool import BaseTool
from .tool_types import ToolKind, ToolErrorType


class ReadFileTool(BaseTool):
    """Enhanced tool for reading files with truncation support and better error handling."""
    Name = "read_file"
    
    # Default limit for file reading to prevent context overflow
    DEFAULT_MAX_LINES = 2000
    
    def __init__(self, working_dir: str):
        super().__init__(
            self.Name,
            """Reads and returns the content of a specified file. If the file is large, the content will be truncated. The tool's response will clearly indicate if truncation has occurred and will provide details on how to read more of the file using the 'offset' and 'limit' parameters. Handles text, images (PNG, JPG, GIF, WEBP, SVG, BMP), and PDF files. For text files, it can read specific line ranges.""",
            {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The absolute path to the file to read (e.g., '/home/user/project/file.txt'). Relative paths are not supported. You must provide an absolute path."
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Optional: For text files, the 0-based line number to start reading from. Requires 'limit' to be set. Use for paginating through large files."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Optional: For text files, maximum number of lines to read. Use with 'offset' to paginate through large files. If omitted, reads the entire file (if feasible, up to a default limit)."
                    }
                },
                "required": ["path"]
            },
            ToolKind.READ
        )
        self.working_dir = working_dir
        
    def validate_params(self, params: Dict[str, Any]) -> str:
        error = super().validate_params(params)
        if error:
            return error
            
        file_path = params["path"]
        if not os.path.isabs(file_path):
            return f"File path must be absolute, but was relative: {file_path}. You must provide an absolute path."
            
        # Check if path is within working directory
        try:
            relative_path = os.path.relpath(file_path, self.working_dir)
            if relative_path.startswith(".."):
                return f"File path must be within the working directory ({self.working_dir}): {file_path}"
        except ValueError:
            return f"Invalid file path: {file_path}"
            
        # Check if file exists
        if not os.path.exists(file_path):
            return "Could not read file because no file was found at the specified path."
            
        if os.path.isdir(file_path):
            return "Could not read file because the provided path is a directory, not a file."
            
        offset = params.get("offset")
        limit = params.get("limit")
        
        if offset is not None and offset < 0:
            return "Offset must be a non-negative number"
            
        if limit is not None and limit <= 0:
            return "Limit must be a positive number"
            
        # Check file size
        try:
            file_size = os.path.getsize(file_path)
            if file_size > 10 * 1024 * 1024:  # 10MB limit
                return f"Could not read file. File size exceeds 10MB limit: {file_size} bytes"
        except OSError:
            pass  # If we can't get the size, we'll let the read operation handle any errors
            
        return None
        
    def get_description(self, params: Dict[str, Any]) -> str:
        """Get a description of the file being read."""
        if not params or "path" not in params or not params["path"].strip():
            return "Model did not provide valid parameters for read file tool, missing or empty \"absolute_path\""
            
        file_path = params["path"]
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
            
        return shortened
        
    def _read_text_file_with_pagination(self, file_path: str, offset: int = 0, limit: int = None) -> Tuple[str, bool, int, int, int]:
        """Read a text file with pagination support.
        
        Returns:
            Tuple of (content, is_truncated, start_line, end_line, total_lines)
        """
        if limit is None:
            limit = self.DEFAULT_MAX_LINES
            
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                
            total_lines = len(lines)
            
            # Apply pagination
            paginated_lines = lines[offset:offset+limit] if limit else lines[offset:]
            content = "".join(paginated_lines)
            
            start_line = offset + 1  # 1-based line numbers
            end_line = min(offset + len(paginated_lines), total_lines)
            is_truncated = len(paginated_lines) < len(lines[offset:]) or (limit and len(lines) > limit)
            
            return content, is_truncated, start_line, end_line, total_lines
            
        except Exception as e:
            raise Exception(f"Error reading text file: {str(e)}")
        
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        error = self.validate_params(params)
        if error:
            # Map error messages to ToolErrorType
            error_type = ToolErrorType.READ_CONTENT_FAILURE
            if "no file was found" in error.lower():
                error_type = ToolErrorType.FILE_NOT_FOUND
            elif "directory" in error.lower():
                error_type = ToolErrorType.INVALID_TOOL_PARAMS
            elif "size exceeds" in error.lower():
                error_type = ToolErrorType.FILE_TOO_LARGE
                
            return {
                "llmContent": error,
                "returnDisplay": error,
                "error": {
                    "message": error,
                    "type": error_type.value
                }
            }
            
        file_path = params["path"]
        offset = params.get("offset", 0)
        limit = params.get("limit")
        
        try:
            # Determine if file is text or binary by reading a small portion
            with open(file_path, "rb") as f:
                sample = f.read(1024)
                
            # Simple check for binary files
            is_binary = b'\x00' in sample or (sample.count(b'\n') < sample.count(b'\x00') * 0.3)
            
            # Handle text files
            if not is_binary:
                content, is_truncated, start_line, end_line, total_lines = self._read_text_file_with_pagination(
                    file_path, offset, limit
                )
                
                if is_truncated:
                    next_offset = offset + (end_line - start_line + 1)
                    llm_content = f"""
IMPORTANT: The file content has been truncated.
Status: Showing lines {start_line}-{end_line} of {total_lines} total lines.
Action: To read more of the file, you can use the 'offset' and 'limit' parameters in a subsequent 'read_file' call. For example, to read the next section of the file, use offset: {next_offset}.

--- FILE CONTENT (truncated) ---
{content}"""
                else:
                    llm_content = content
                    
                return {
                    "llmContent": llm_content,
                    "returnDisplay": content
                }
                
            # Handle binary files (images, PDFs, etc.)
            else:
                with open(file_path, "rb") as f:
                    content = f.read()
                    
                # Guess MIME type
                mime_type, _ = mimetypes.guess_type(file_path)
                if not mime_type:
                    mime_type = "application/octet-stream"
                    
                # Encode binary content as base64
                encoded = base64.b64encode(content).decode("utf-8")
                return {
                    "llmContent": {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{encoded}"
                        }
                    },
                    "returnDisplay": f"Read binary file: {os.path.basename(file_path)}"
                }
                
        except Exception as e:
            return {
                "llmContent": f"Could not read file. {str(e)}",
                "returnDisplay": f"Error reading file: {str(e)}",
                "error": {
                    "message": str(e),
                    "type": ToolErrorType.READ_CONTENT_FAILURE.value
                }
            }


class WriteFileTool(BaseTool):
    """Enhanced tool for writing files with better validation, error handling, and user confirmation support."""
    Name = "write_file"
    
    def __init__(self, working_dir: str):
        super().__init__(
            self.Name,
            """Writes content to a specified file in the local filesystem.

      The user has the ability to modify `content`. If modified, this will be stated in the response.""",
            {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The absolute path to the file to write to (e.g., '/home/user/project/file.txt'). Relative paths are not supported."
                    },
                    "content": {
                        "type": "string",
                        "description": "The content to write to the file."
                    }
                },
                "required": ["path", "content"]
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
            
        # Check if parent directory exists and is accessible
        parent_dir = os.path.dirname(file_path)
        if parent_dir:
            if not os.path.exists(parent_dir):
                # Try to create parent directories
                try:
                    os.makedirs(parent_dir, exist_ok=True)
                except PermissionError:
                    return f"Permission denied: Cannot create parent directory: {parent_dir}"
                except Exception as e:
                    return f"Cannot create parent directory '{parent_dir}': {str(e)}"
            elif not os.path.isdir(parent_dir):
                return f"Parent path is not a directory: {parent_dir}"
                
        # If file exists, check if it's actually a file
        if os.path.exists(file_path):
            if os.path.isdir(file_path):
                return f"Path is a directory, not a file: {file_path}"
                
        return None
        
    def get_description(self, params: Dict[str, Any]) -> str:
        """Get a description of the file being written."""
        if not params.get("path"):
            return "Model did not provide valid parameters for write file tool, missing or empty \"file_path\""
            
        file_path = params["path"]
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
            
        return f"Writing to {shortened}"
        
    def should_confirm_execute(self, params: Dict[str, Any]) -> None:
        """Check if tool execution should be confirmed.
        
        In the enhanced version, this could be used to show diffs or confirmations,
        but for now we'll implement a basic version.
        """
        return None
        
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        error = self.validate_params(params)
        if error:
            return {
                "llmContent": f"Could not write file due to invalid parameters: {error}",
                "returnDisplay": error,
                "error": {
                    "message": error,
                    "type": "invalid_tool_params"
                }
            }
            
        file_path = params["path"]
        content = params["content"]
        modified_by_user = params.get("modified_by_user", False)
        ai_proposed_content = params.get("ai_proposed_content", content)
        
        try:
            # Create parent directories if needed
            parent_dir = os.path.dirname(file_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            
            # Check if file already exists
            file_exists = os.path.exists(file_path)
            
            # Write file
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
                
            # Prepare success message
            success_message_parts = [
                f"Successfully {'created and wrote to new file' if not file_exists else 'overwrote file'}: {file_path}."
            ]
            if modified_by_user:
                success_message_parts.append(f"User modified the `content` to be: {content}")
                
            return {
                "llmContent": " ".join(success_message_parts),
                "returnDisplay": f"Successfully wrote to file: {file_path}"
            }
            
        except PermissionError as e:
            error_msg = f"Permission denied writing to file: {file_path} (EACCES)"
            return {
                "llmContent": error_msg,
                "returnDisplay": error_msg,
                "error": {
                    "message": error_msg,
                    "type": "permission_denied"
                }
            }
        except OSError as e:
            if e.errno == 28:  # No space left on device
                error_msg = f"No space left on device: {file_path} (ENOSPC)"
                return {
                    "llmContent": error_msg,
                    "returnDisplay": error_msg,
                    "error": {
                        "message": error_msg,
                        "type": "no_space_left"
                    }
                }
            elif e.errno == 21:  # Is a directory
                error_msg = f"Target is a directory, not a file: {file_path} (EISDIR)"
                return {
                    "llmContent": error_msg,
                    "returnDisplay": error_msg,
                    "error": {
                        "message": error_msg,
                        "type": "target_is_directory"
                    }
                }
            else:
                error_msg = f"Error writing to file '{file_path}': {str(e)} ({getattr(e, 'errno', 'unknown')})"
                return {
                    "llmContent": error_msg,
                    "returnDisplay": error_msg,
                    "error": {
                        "message": error_msg,
                        "type": "file_write_failure"
                    }
                }
        except Exception as e:
            error_msg = f"Error writing to file: {str(e)}"
            return {
                "llmContent": error_msg,
                "returnDisplay": error_msg,
                "error": {
                    "message": error_msg,
                    "type": "file_write_failure"
                }
            }


class ListDirectoryTool(BaseTool):
    """Enhanced tool for listing directory contents with better filtering and git ignore support."""
    Name = "list_directory"
    
    def __init__(self, working_dir: str):
        super().__init__(
            self.Name,
            "Lists the names of files and subdirectories directly within a specified directory path. Can optionally ignore entries matching provided glob patterns.",
            {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The absolute path to the directory to list (must be absolute, not relative)"
                    },
                    "ignore": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "List of glob patterns to ignore"
                    },
                    "file_filtering_options": {
                        "type": "object",
                        "description": "Optional: Whether to respect ignore patterns from .gitignore or .geminiignore",
                        "properties": {
                            "respect_git_ignore": {
                                "type": "boolean",
                                "description": "Optional: Whether to respect .gitignore patterns when listing files. Only available in git repositories. Defaults to true."
                            },
                            "respect_gemini_ignore": {
                                "type": "boolean",
                                "description": "Optional: Whether to respect .geminiignore patterns when listing files. Defaults to true."
                            }
                        }
                    }
                },
                "required": ["path"]
            },
            ToolKind.SEARCH
        )
        self.working_dir = working_dir
        
    def validate_params(self, params: Dict[str, Any]) -> str:
        error = super().validate_params(params)
        if error:
            return error
            
        dir_path = params["path"]
        if not os.path.isabs(dir_path):
            return f"Path must be absolute: {dir_path}"
            
        # Check if path is within working directory
        try:
            relative_path = os.path.relpath(dir_path, self.working_dir)
            if relative_path.startswith(".."):
                return f"Path must be within the working directory ({self.working_dir}): {dir_path}"
        except ValueError:
            return f"Invalid path: {dir_path}"
            
        if not os.path.exists(dir_path):
            return "Directory not found or inaccessible"
            
        if not os.path.isdir(dir_path):
            return "Path is not a directory"
            
        return None
        
    def should_ignore(self, filename: str, patterns: List[str] = None) -> bool:
        """Check if a filename matches any of the ignore patterns."""
        if not patterns:
            return False
            
        for pattern in patterns:
            if fnmatch.fnmatch(filename, pattern):
                return True
                
        return False
        
    def get_description(self, params: Dict[str, Any]) -> str:
        """Get a description of the directory being listed."""
        dir_path = params.get("path", "")
        try:
            relative_path = os.path.relpath(dir_path, self.working_dir)
        except ValueError:
            relative_path = dir_path
            
        # Shorten path for display
        path_parts = relative_path.split(os.sep)
        if len(path_parts) > 3:
            shortened = os.sep.join(["..."] + path_parts[-3:])
        else:
            shortened = relative_path
            
        return shortened
        
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        error = self.validate_params(params)
        if error:
            return {
                "llmContent": f"Error: Invalid parameters provided. Reason: {error}",
                "returnDisplay": f"Error: Failed to execute tool."
            }
            
        dir_path = params["path"]
        ignore_patterns = params.get("ignore", [])
        file_filtering_options = params.get("file_filtering_options", {})
        respect_git_ignore = file_filtering_options.get("respect_git_ignore", True)
        respect_gemini_ignore = file_filtering_options.get("respect_gemini_ignore", True)
        
        try:
            entries = os.listdir(dir_path)
            
            if not entries:
                return {
                    "llmContent": f"Directory {dir_path} is empty.",
                    "returnDisplay": "Directory is empty."
                }
            
            # Filter entries based on ignore patterns
            filtered_entries = []
            git_ignored_count = 0
            gemini_ignored_count = 0
            
            for entry in entries:
                if self.should_ignore(entry, ignore_patterns):
                    continue
                    
                full_path = os.path.join(dir_path, entry)
                
                # Check for git ignore (simplified implementation)
                if respect_git_ignore and entry in ['.git', 'node_modules']:
                    git_ignored_count += 1
                    continue
                    
                # Check for gemini ignore (simplified implementation)
                if respect_gemini_ignore and entry.endswith('.geminiignore'):
                    gemini_ignored_count += 1
                    continue
                    
                is_dir = os.path.isdir(full_path)
                try:
                    size = 0 if is_dir else os.path.getsize(full_path)
                    modified_time = os.path.getmtime(full_path)
                except OSError:
                    # If we can't get file stats, use defaults
                    size = 0
                    modified_time = 0
                    
                filtered_entries.append({
                    "name": entry,
                    "path": full_path,
                    "isDirectory": is_dir,
                    "size": size,
                    "modifiedTime": modified_time
                })
            
            # Sort entries (directories first, then alphabetically)
            filtered_entries.sort(key=lambda x: (not x["isDirectory"], x["name"]))
            
            # Create formatted content for LLM
            directory_content = "\n".join([
                f"[DIR] {entry['name']}" if entry["isDirectory"] else entry["name"]
                for entry in filtered_entries
            ])
            
            result_message = f"Directory listing for {dir_path}:\n{directory_content}"
            
            # Add ignored file information
            ignored_messages = []
            if git_ignored_count > 0:
                ignored_messages.append(f"{git_ignored_count} git-ignored")
            if gemini_ignored_count > 0:
                ignored_messages.append(f"{gemini_ignored_count} gemini-ignored")
                
            if ignored_messages:
                result_message += f"\n\n({', '.join(ignored_messages)})"
            
            display_message = f"Listed {len(filtered_entries)} item(s)."
            if ignored_messages:
                display_message += f" ({', '.join(ignored_messages)})"
            
            return {
                "llmContent": result_message,
                "returnDisplay": display_message
            }
            
        except PermissionError:
            return {
                "llmContent": f"Error: Permission denied accessing directory: {dir_path}",
                "returnDisplay": "Error: Permission denied."
            }
        except Exception as e:
            return {
                "llmContent": f"Error listing directory: {str(e)}",
                "returnDisplay": "Error: Failed to list directory."
            }


class GlobTool(BaseTool):
    """Enhanced tool for finding files matching a pattern with better sorting and filtering."""
    Name = "glob"
    
    def __init__(self, working_dir: str):
        super().__init__(
            self.Name,
            "Efficiently finds files matching specific glob patterns (e.g., `src/**/*.ts`, `**/*.md`), returning absolute paths sorted by modification time (newest first). Ideal for quickly locating files based on their name or path structure, especially in large codebases.",
            {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "The glob pattern to match against (e.g., '**/*.py', 'docs/*.md')."
                    },
                    "path": {
                        "type": "string",
                        "description": "Optional: The absolute path to the directory to search within. If omitted, searches the root directory."
                    },
                    "case_sensitive": {
                        "type": "boolean",
                        "description": "Optional: Whether the search should be case-sensitive. Defaults to false."
                    },
                    "respect_git_ignore": {
                        "type": "boolean",
                        "description": "Optional: Whether to respect .gitignore patterns when finding files. Only available in git repositories. Defaults to true."
                    }
                },
                "required": ["pattern"]
            },
            ToolKind.SEARCH
        )
        self.working_dir = working_dir
        
    def validate_params(self, params: Dict[str, Any]) -> str:
        error = super().validate_params(params)
        if error:
            return error
            
        pattern = params["pattern"]
        if not pattern or not pattern.strip():
            return "The 'pattern' parameter cannot be empty."
            
        search_path = params.get("path", "")
        if search_path:
            search_dir_absolute = os.path.join(self.working_dir, search_path)
            if not os.path.exists(search_dir_absolute):
                return f"Search path does not exist {search_dir_absolute}"
                
            if not os.path.isdir(search_dir_absolute):
                return f"Search path is not a directory: {search_dir_absolute}"
                
            # Check if path is within working directory
            try:
                relative_path = os.path.relpath(search_dir_absolute, self.working_dir)
                if relative_path.startswith(".."):
                    return f"Search path (\"{search_dir_absolute}\") resolves outside the working directory (\"{self.working_dir}\")"
            except ValueError:
                return f"Invalid search path: {search_dir_absolute}"
                
        return None
        
    def get_description(self, params: Dict[str, Any]) -> str:
        """Get a description of the glob operation."""
        pattern = params.get("pattern", "")
        search_path = params.get("path", "")
        
        description = f"'{pattern}'"
        if search_path:
            search_dir = os.path.join(self.working_dir, search_path)
            try:
                relative_path = os.path.relpath(search_dir, self.working_dir)
            except ValueError:
                relative_path = search_path
                
            # Shorten path for display
            path_parts = relative_path.split(os.sep)
            if len(path_parts) > 3:
                shortened = os.sep.join(["..."] + path_parts[-3:])
            else:
                shortened = relative_path
                
            description += f" within {shortened}"
        else:
            description += " within root directory"
            
        return description
        
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        error = self.validate_params(params)
        if error:
            return {
                "llmContent": f"Error: Invalid parameters provided. Reason: {error}",
                "returnDisplay": error
            }
            
        import glob
        import fnmatch
        pattern = params["pattern"]
        search_path = params.get("path", "")
        case_sensitive = params.get("case_sensitive", False)
        respect_git_ignore = params.get("respect_git_ignore", True)
        
        try:
            search_dir_absolute = os.path.join(self.working_dir, search_path) if search_path else self.working_dir
            
            # Find files matching pattern
            matches = glob.glob(
                os.path.join(search_dir_absolute, pattern),
                recursive=True
            )
            
            # Filter out directories and apply ignore patterns
            file_matches = []
            git_ignored_count = 0
            
            default_ignores = [
                '**/node_modules/**', '**/.git/**', '**/.vscode/**', '**/.idea/**',
                '**/dist/**', '**/build/**', '**/coverage/**', '**/__pycache__/**'
            ]
            
            for match in matches:
                if not os.path.isfile(match):
                    continue
                    
                # Check if file should be ignored
                should_ignore = False
                relative_match = os.path.relpath(match, self.working_dir)
                
                # Check default ignores
                for ignore_pattern in default_ignores:
                    if fnmatch.fnmatch(relative_match, ignore_pattern.replace('**/', '').replace('/**', '')):
                        should_ignore = True
                        break
                        
                # Check git ignore (simplified)
                if not should_ignore and respect_git_ignore:
                    path_parts = relative_match.split(os.sep)
                    if '.git' in path_parts or 'node_modules' in path_parts:
                        should_ignore = True
                        git_ignored_count += 1
                        
                if not should_ignore:
                    file_matches.append(match)
            
            if not file_matches:
                ignore_msg = f" ({git_ignored_count} files were git-ignored)" if git_ignored_count > 0 else ""
                search_location = search_path if search_path else "root directory"
                return {
                    "llmContent": f"No files found matching pattern \"{pattern}\" within {search_dir_absolute}{ignore_msg}.",
                    "returnDisplay": "No files found"
                }
            
            # Sort by modification time (newest first)
            def get_mtime(filepath):
                try:
                    return os.path.getmtime(filepath)
                except OSError:
                    return 0
                    
            file_matches.sort(key=get_mtime, reverse=True)
            
            # Limit results to prevent context overflow
            max_results = 100
            truncated = len(file_matches) > max_results
            if truncated:
                file_matches = file_matches[:max_results]
            
            # Format results
            file_list_description = "\n".join(file_matches)
            file_count = len(file_matches)
            
            search_location = f"within {search_dir_absolute}" if search_path else "within root directory"
            ignore_msg = f" ({git_ignored_count} additional files were git-ignored)" if git_ignored_count > 0 else ""
            truncation_msg = f" (showing first {max_results} of {len(file_matches) + (max_results if truncated else 0)}+ total matches)" if truncated else ""
            
            result_message = f"Found {file_count} file(s) matching \"{pattern}\" {search_location}{ignore_msg}{truncation_msg}, sorted by modification time (newest first):\n{file_list_description}"
            
            display_msg = f"Found {file_count} matching file(s)"
            if truncated:
                display_msg += f" (truncated from {len(file_matches) + (max_results if truncated else 0)}+)"
                
            return {
                "llmContent": result_message,
                "returnDisplay": display_msg
            }
            
        except Exception as e:
            return {
                "llmContent": f"Error during glob search operation: {str(e)}",
                "returnDisplay": "Error: An unexpected error occurred."
            }