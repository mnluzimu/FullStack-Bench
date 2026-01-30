"""
Enhanced read many files tool for Qwen Code Python implementation with better file handling and filtering.
"""
import os
import glob
import base64
import mimetypes
from typing import Dict, Any, List
from .base_tool import BaseTool
from .tool_types import ToolKind


# Default exclusion patterns for commonly ignored directories and binary file types
DEFAULT_EXCLUDES = [
    "**/node_modules/**",
    "**/.git/**",
    "**/.vscode/**",
    "**/.idea/**",
    "**/dist/**",
    "**/build/**",
    "**/coverage/**",
    "**/__pycache__/**",
    "**/*.pyc",
    "**/*.pyo",
    "**/*.bin",
    "**/*.exe",
    "**/*.dll",
    "**/*.so",
    "**/*.dylib",
    "**/*.class",
    "**/*.jar",
    "**/*.war",
    "**/*.zip",
    "**/*.tar",
    "**/*.gz",
    "**/*.bz2",
    "**/*.rar",
    "**/*.7z",
    "**/*.doc",
    "**/*.docx",
    "**/*.xls",
    "**/*.xlsx",
    "**/*.ppt",
    "**/*.pptx",
    "**/*.odt",
    "**/*.ods",
    "**/*.odp",
    "**/*.DS_Store",
    "**/.env"
]

DEFAULT_OUTPUT_SEPARATOR_FORMAT = "--- {filePath} ---"


class ReadManyFilesTool(BaseTool):
    """Enhanced tool for reading content from multiple files with better filtering and binary file support."""
    Name = "read_many_files"
    
    def __init__(self, working_dir: str):
        super().__init__(
            self.Name,
            "Reads content from multiple files specified by paths or glob patterns within a configured target directory. For text files, it concatenates their content into a single string. It is primarily designed for text-based files. However, it can also process image (e.g., .png, .jpg) and PDF (.pdf) files if their file names or extensions are explicitly included in the 'paths' argument. For these explicitly requested non-text files, their data is read and included in a format suitable for model consumption (e.g., base64 encoded).\n\nThis tool is useful when you need to understand or analyze a collection of files, such as:\n- Getting an overview of a codebase or parts of it (e.g., all TypeScript files in the 'src' directory).\n- Finding where specific functionality is implemented if the user asks broad questions about code.\n- Reviewing documentation files (e.g., all Markdown files in the 'docs' directory).\n- Gathering context from multiple configuration files.\n- When the user asks to \"read all files in X directory\" or \"show me the content of all Y files\".\n\nUse this tool when the user's query implies needing the content of several files simultaneously for context, analysis, or summarization. For text files, it uses default UTF-8 encoding and a '--- {filePath} ---' separator between file contents. Ensure paths are relative to the target directory. Glob patterns like 'src/**/*.js' are supported. Avoid using for single files if a more specific single-file reading tool is available, unless the user specifically requests to process a list containing just one file via this tool. Other binary files (not explicitly requested as image/PDF) are generally skipped. Default excludes apply to common non-text files (except for explicitly requested images/PDFs) and large dependency directories unless 'useDefaultExcludes' is false.",
            {
                "type": "object",
                "properties": {
                    "paths": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "minLength": 1
                        },
                        "minItems": 1,
                        "description": "Required. An array of glob patterns or paths relative to the tool's target directory. Examples: ['src/**/*.ts'], ['README.md', 'docs/']"
                    },
                    "exclude": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "default": [],
                        "description": "Optional. Glob patterns for files/directories to exclude. Added to default excludes if useDefaultExcludes is true. Example: \"**/*.log\", \"temp/\""
                    },
                    "include": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "default": [],
                        "description": "Optional. Additional glob patterns to include. These are merged with `paths`. Example: \"*.test.ts\" to specifically add test files if they were broadly excluded."
                    },
                    "recursive": {
                        "type": "boolean",
                        "default": True,
                        "description": "Optional. Whether to search recursively (primarily controlled by `**` in glob patterns). Defaults to true."
                    },
                    "useDefaultExcludes": {
                        "type": "boolean",
                        "default": True,
                        "description": "Optional. Whether to apply a list of default exclusion patterns (e.g., node_modules, .git, binary files). Defaults to true."
                    },
                    "file_filtering_options": {
                        "type": "object",
                        "description": "Whether to respect ignore patterns from .gitignore or .geminiignore",
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
                "required": ["paths"]
            },
            ToolKind.READ
        )
        self.working_dir = working_dir
        
    def validate_params(self, params: Dict[str, Any]) -> str:
        error = super().validate_params(params)
        if error:
            return error
            
        paths = params["paths"]
        if not paths or not isinstance(paths, list):
            return "The 'paths' parameter must be a non-empty list."
            
        for path in paths:
            if not isinstance(path, str) or not path.strip():
                return "All paths must be non-empty strings."
                
        return None
        
    def get_description(self, params: Dict[str, Any]) -> str:
        """Get a description of the read many files operation."""
        paths = params.get("paths", [])
        include = params.get("include", [])
        exclude = params.get("exclude", [])
        use_default_excludes = params.get("useDefaultExcludes", True)
        
        all_patterns = paths + include
        path_desc = f"using patterns: \n{', '.join(all_patterns)}\n (within target directory: \n{self.working_dir}\n) "
        
        # Determine the final list of exclusion patterns
        param_excludes = exclude or []
        param_use_default_excludes = use_default_excludes is not False
        final_exclusion_patterns_for_description = param_excludes + (DEFAULT_EXCLUDES if param_use_default_excludes else [])
        
        exclude_desc = f"Excluding: {len(final_exclusion_patterns_for_description)} patterns" if final_exclusion_patterns_for_description else "Excluding: none specified"
        
        return f"Will attempt to read and concatenate files {path_desc}. {exclude_desc}. File encoding: UTF-8. Separator: \"{DEFAULT_OUTPUT_SEPARATOR_FORMAT.format(filePath='path/to/file.ext')}\"."
        
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        error = self.validate_params(params)
        if error:
            return {
                "llmContent": f"Error: Invalid parameters provided. Reason: {error}",
                "returnDisplay": f"Error: {error}"
            }
            
        paths = params["paths"]
        exclude_patterns = params.get("exclude", [])
        include_patterns = params.get("include", [])
        recursive = params.get("recursive", True)
        use_default_excludes = params.get("useDefaultExcludes", True)
        file_filtering_options = params.get("file_filtering_options", {})
        respect_git_ignore = file_filtering_options.get("respect_git_ignore", True)
        respect_gemini_ignore = file_filtering_options.get("respect_gemini_ignore", True)
        
        try:
            # Combine exclude patterns
            effective_excludes = (DEFAULT_EXCLUDES if use_default_excludes else []) + exclude_patterns
            
            # Find all matching files
            all_files = set()
            
            # Process paths patterns
            search_patterns = paths + include_patterns
            if not search_patterns:
                return {
                    "llmContent": "No search paths or include patterns provided.",
                    "returnDisplay": "## Information\n\nNo search paths or include patterns were specified. Nothing to read or concatenate."
                }
            
            for pattern in search_patterns:
                # Convert pattern to be compatible with glob
                full_pattern = os.path.join(self.working_dir, pattern.replace("\\", "/"))
                try:
                    matched_files = glob.glob(full_pattern, recursive=True)
                    # Filter out directories
                    matched_files = [f for f in matched_files if os.path.isfile(f)]
                    all_files.update(matched_files)
                except Exception:
                    # Skip invalid patterns
                    continue
            
            # Apply exclusion filters
            filtered_files = []
            skipped_files = []
            
            for file_path in all_files:
                should_exclude = False
                relative_path = os.path.relpath(file_path, self.working_dir).replace("\\", "/")
                
                # Check if file is within working directory
                if relative_path.startswith("../"):
                    skipped_files.append({
                        "path": file_path,
                        "reason": "Security: File outside working directory"
                    })
                    continue
                
                # Check exclude patterns
                for exclude_pattern in effective_excludes:
                    if glob.fnmatch.fnmatch(relative_path, exclude_pattern.replace("**/", "").replace("/**", "")) or \
                       glob.fnmatch.fnmatch(file_path, exclude_pattern):
                        should_exclude = True
                        break
                
                # Check git ignore (simplified implementation)
                if not should_exclude and respect_git_ignore:
                    path_parts = relative_path.split("/")
                    if ".git" in path_parts or "node_modules" in path_parts:
                        should_exclude = True
                
                if not should_exclude:
                    filtered_files.append(file_path)
            
            if not filtered_files:
                return {
                    "llmContent": "No files matching the criteria were found or all were skipped.",
                    "returnDisplay": "## Information\n\nNo files matching the criteria were found or all were skipped."
                }
            
            # Sort files for consistent output
            filtered_files.sort()
            
            # Read content from each file
            content_parts = []
            processed_files_relative_paths = []
            skipped_files_details = []
            
            for file_path in filtered_files:
                try:
                    relative_path = os.path.relpath(file_path, self.working_dir).replace("\\", "/")
                    
                    # Determine if file is text or binary by reading a small portion
                    with open(file_path, "rb") as f:
                        sample = f.read(1024)
                    
                    # Simple check for binary files
                    is_binary = b'\x00' in sample or (sample.count(b'\n') < sample.count(b'\x00') * 0.3)
                    
                    # Handle text files
                    if not is_binary:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                        
                        # Check if content is too large
                        lines = content.splitlines()
                        is_truncated = len(lines) > 2000
                        if is_truncated:
                            content = "\n".join(lines[:2000])
                            content = f"[WARNING: This file was truncated. To view the full content, use the 'read_file' tool on this specific file.]\n\n{content}"
                        
                        separator = DEFAULT_OUTPUT_SEPARATOR_FORMAT.format(filePath=file_path)
                        content_parts.append(f"{separator}\n\n{content}\n\n")
                        processed_files_relative_paths.append(relative_path)
                    else:
                        # Handle binary files (images, PDFs, etc.)
                        # Check if this is an explicitly requested binary file
                        is_explicitly_requested = False
                        file_extension = os.path.splitext(file_path)[1].lower()
                        file_name = os.path.basename(file_path)
                        
                        for pattern in search_patterns:
                            if file_extension in pattern.lower() or file_name in pattern:
                                is_explicitly_requested = True
                                break
                        
                        if is_explicitly_requested:
                            with open(file_path, "rb") as f:
                                content = f.read()
                            
                            # Guess MIME type
                            mime_type, _ = mimetypes.guess_type(file_path)
                            if not mime_type:
                                mime_type = "application/octet-stream"
                            
                            # Encode binary content as base64
                            encoded = base64.b64encode(content).decode("utf-8")
                            content_parts.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{encoded}"
                                }
                            })
                            processed_files_relative_paths.append(relative_path)
                        else:
                            skipped_files_details.append({
                                "path": relative_path,
                                "reason": "binary file (image/pdf) was not explicitly requested by name or extension"
                            })
                    
                except PermissionError:
                    relative_path = os.path.relpath(file_path, self.working_dir).replace("\\", "/")
                    skipped_files_details.append({
                        "path": relative_path,
                        "reason": "Permission denied"
                    })
                except Exception as e:
                    relative_path = os.path.relpath(file_path, self.working_dir).replace("\\", "/")
                    skipped_files_details.append({
                        "path": relative_path,
                        "reason": f"Unexpected error: {str(e)}"
                    })
            
            # Format display message
            display_message = f"### ReadManyFiles Result (Target Dir: `{self.working_dir}`)\n\n"
            
            if processed_files_relative_paths:
                display_message += f"Successfully read and concatenated content from **{len(processed_files_relative_paths)} file(s)**.\n"
                if len(processed_files_relative_paths) <= 10:
                    display_message += "\n**Processed Files:**\n"
                    for p in processed_files_relative_paths:
                        display_message += f"- `{p}`\n"
                else:
                    display_message += f"\n**Processed Files (first 10 shown):**\n"
                    for p in processed_files_relative_paths[:10]:
                        display_message += f"- `{p}`\n"
                    display_message += f"- ...and {len(processed_files_relative_paths) - 10} more.\n"
            
            if skipped_files_details:
                if not processed_files_relative_paths:
                    display_message += "No files were read and concatenated based on the criteria.\n"
                if len(skipped_files_details) <= 5:
                    display_message += f"\n**Skipped {len(skipped_files_details)} item(s):**\n"
                else:
                    display_message += f"\n**Skipped {len(skipped_files_details)} item(s) (first 5 shown):**\n"
                for f in skipped_files_details[:5]:
                    display_message += f"- `{f['path']}` (Reason: {f['reason']})\n"
                if len(skipped_files_details) > 5:
                    display_message += f"- ...and {len(skipped_files_details) - 5} more.\n"
            elif not processed_files_relative_paths and not skipped_files_details:
                display_message += "No files were read and concatenated based on the criteria.\n"
            
            # Return result
            if not content_parts:
                content_parts = ["No files matching the criteria were found or all were skipped."]
                
            return {
                "llmContent": content_parts if len(content_parts) > 1 else content_parts[0],
                "returnDisplay": display_message.strip()
            }
            
        except Exception as e:
            return {
                "llmContent": f"Error during file search: {str(e)}",
                "returnDisplay": f"## File Search Error\n\nAn error occurred while searching for files:\n```\n{str(e)}\n```"
            }
