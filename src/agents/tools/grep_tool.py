"""
Enhanced grep tool for Qwen Code Python implementation with better search capabilities and filtering.
"""
import os
import re
import fnmatch
from typing import Dict, Any, List
from .base_tool import BaseTool
from .tool_types import ToolKind


class GrepTool(BaseTool):
    """Enhanced tool for searching for a regular expression pattern within the content of files."""
    Name = "search_file_content"
    
    def __init__(self, working_dir: str):
        super().__init__(
            self.Name,
            "Searches for a regular expression pattern within the content of files in a specified directory (or current working directory). Can filter files by a glob pattern. Returns the lines containing matches, along with their file paths and line numbers.",
            {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "The regular expression (regex) pattern to search for within file contents (e.g., 'function\\\\s+myFunction', 'import\\\\s+\\\\{.*\\\\}\\\\s+from\\\\s+.*')."
                    },
                    "path": {
                        "type": "string",
                        "description": "Optional: The absolute path to the directory to search within. If omitted, searches the current working directory."
                    },
                    "include": {
                        "type": "string",
                        "description": "Optional: A glob pattern to filter which files are searched (e.g., '*.js', '*.{ts,tsx}', 'src/**'). If omitted, searches all files (respecting potential global ignores)."
                    },
                    "maxResults": {
                        "type": "integer",
                        "description": "Optional: Maximum number of matches to return to prevent context overflow (default: 20, max: 100). Use lower values for broad searches, higher for specific searches.",
                        "minimum": 1,
                        "maximum": 100
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
            
        try:
            re.compile(pattern)
        except re.error as e:
            return f"Invalid regular expression pattern provided: {pattern}. Error: {str(e)}"
            
        search_path = params.get("path")
        if search_path:
            if not os.path.isabs(search_path):
                return "Path must be absolute."
            # Check if path is within working directory
            try:
                relative_path = os.path.relpath(search_path, self.working_dir)
                if relative_path.startswith(".."):
                    return f"Path validation failed: Attempted path \"{search_path}\" resolves outside the allowed working directory: {self.working_dir}"
            except ValueError:
                return f"Invalid path: {search_path}"
            if not os.path.exists(search_path):
                return "Path does not exist."
            if not os.path.isdir(search_path):
                return "Path is not a directory."
                
        max_results = params.get("maxResults")
        if max_results is not None:
            if not isinstance(max_results, int) or max_results < 1 or max_results > 100:
                return f"maxResults must be an integer between 1 and 100, got: {max_results}"
                
        return None
        
    def get_description(self, params: Dict[str, Any]) -> str:
        """Get a description of the grep operation."""
        pattern = params.get("pattern", "")
        search_path = params.get("path", "")
        include = params.get("include", "")
        
        description = f"'{pattern}'"
        if include:
            description += f" in {include}"
        if search_path:
            try:
                resolved_path = os.path.join(self.working_dir, search_path) if search_path else self.working_dir
                if resolved_path == self.working_dir or search_path == ".":
                    description += " within ./"
                else:
                    relative_path = os.path.relpath(resolved_path, self.working_dir)
                    # Shorten path for display
                    path_parts = relative_path.split(os.sep)
                    if len(path_parts) > 3:
                        shortened = os.sep.join(["..."] + path_parts[-3:])
                    else:
                        shortened = relative_path
                    description += f" within {shortened}"
            except ValueError:
                description += f" within {search_path}"
        else:
            description += " within the workspace directory"
            
        return description
        
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        error = self.validate_params(params)
        if error:
            return {
                "llmContent": f"Error during grep search operation: {error}",
                "returnDisplay": f"Error: {error}"
            }
            
        import glob
        pattern = params["pattern"]
        search_path = params.get("path", self.working_dir)
        include_pattern = params.get("include")
        max_results = params.get("maxResults", 20)
        
        try:
            # Compile the regex pattern (case insensitive)
            regex = re.compile(pattern, re.IGNORECASE)
            
            # Determine files to search
            if include_pattern:
                # Use glob pattern to filter files
                files_to_search = glob.glob(
                    os.path.join(search_path, include_pattern),
                    recursive=True
                )
                # Filter out directories
                files_to_search = [f for f in files_to_search if os.path.isfile(f)]
            else:
                # Search all files in the directory recursively
                files_to_search = []
                # Define directories to exclude
                exclude_dirs = {
                    '.git', 'node_modules', 'bower_components', '__pycache__',
                    '.next', '.nuxt', 'dist', 'build', 'target', 'coverage',
                    '.vscode', '.idea', '.pytest_cache', '.mypy_cache',
                    '.DS_Store', 'Thumbs.db'
                }
                
                for root, dirs, files in os.walk(search_path):
                    # Skip common ignored directories
                    dirs[:] = [d for d in dirs if d not in exclude_dirs]
                    for file in files:
                        # Skip common ignored files
                        if not any(fnmatch.fnmatch(file, pattern) for pattern in [
                            '*.pyc', '*.pyo', '*.class', '*.jar', '*.log',
                            '*.tmp', '*.temp', '.DS_Store', 'Thumbs.db'
                        ]):
                            files_to_search.append(os.path.join(root, file))
            
            # Apply default exclusions
            default_excludes = [
                '**/node_modules/**', '**/.git/**', '**/.next/**', '**/.nuxt/**',
                '**/.vscode/**', '**/.idea/**', '**/dist/**', '**/build/**',
                '**/target/**', '**/coverage/**', '**/__pycache__/**',
                '**/.pytest_cache/**', '**/.mypy_cache/**',
                '**/*.pyc', '**/*.pyo', '**/*.class', '**/*.jar', '**/*.log',
                '**/*.tmp', '**/*.temp', '**/.DS_Store', '**/Thumbs.db'
            ]
            
            filtered_files = []
            for file_path in files_to_search:
                should_exclude = False
                relative_path = os.path.relpath(file_path, self.working_dir).replace("\\", "/")
                
                # Check if file is within working directory
                if relative_path.startswith("../"):
                    continue
                
                # Check exclude patterns
                for exclude_pattern in default_excludes:
                    if fnmatch.fnmatch(relative_path, exclude_pattern.replace('**/', '').replace('/**', '')):
                        should_exclude = True
                        break
                        
                if not should_exclude:
                    filtered_files.append(file_path)
            
            matches = []
            files_searched = 0
            total_matches_found = 0
            search_truncated = False
            
            for file_path in filtered_files:
                # Check if we've reached the max results
                if len(matches) >= max_results:
                    search_truncated = True
                    break
                    
                files_searched += 1
                
                try:
                    # Try to read the file as text
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                        
                    # Search for matches in each line
                    file_matches = []
                    for line_num, line in enumerate(lines, 1):
                        if regex.search(line):
                            file_matches.append({
                                "file": file_path,
                                "line": line_num,
                                "content": line.rstrip()
                            })
                    
                    total_matches_found += len(file_matches)
                    
                    # Add matches up to max_results
                    remaining_slots = max_results - len(matches)
                    if remaining_slots <= 0:
                        search_truncated = True
                        break
                    
                    if len(file_matches) > remaining_slots:
                        matches.extend(file_matches[:remaining_slots])
                        search_truncated = True
                        break
                    else:
                        matches.extend(file_matches)
                        
                except (PermissionError, OSError):
                    # Skip files that can't be read due to permissions or other OS errors
                    continue
                except Exception:
                    # Skip files that cause other errors
                    continue
            
            # Group matches by file
            matches_by_file = {}
            for match in matches:
                file_key = match["file"]
                if file_key not in matches_by_file:
                    matches_by_file[file_key] = []
                matches_by_file[file_key].append(match)
            
            # Sort matches within each file by line number
            for file_matches in matches_by_file.values():
                file_matches.sort(key=lambda x: x["line"])
            
            if not matches:
                search_location_description = "in the workspace directory"
                if search_path != self.working_dir:
                    try:
                        relative_search_path = os.path.relpath(search_path, self.working_dir)
                        search_location_description = f"in path \"{relative_search_path}\""
                    except ValueError:
                        search_location_description = f"in path \"{search_path}\""
                
                filter_description = ""
                if include_pattern:
                    filter_description = f" (filter: \"{include_pattern}\")"
                
                no_match_msg = f"No matches found for pattern \"{pattern}\" {search_location_description}{filter_description}."
                return {
                    "llmContent": no_match_msg,
                    "returnDisplay": "No matches found"
                }
            
            # Format results
            match_count = len(matches)
            match_term = "match" if match_count == 1 else "matches"
            
            # Build the header with truncation info if needed
            search_location_description = "in the workspace directory"
            if search_path != self.working_dir:
                try:
                    relative_search_path = os.path.relpath(search_path, self.working_dir)
                    search_location_description = f"in path \"{relative_search_path}\""
                except ValueError:
                    search_location_description = f"in path \"{search_path}\""
            
            filter_description = ""
            if include_pattern:
                filter_description = f" (filter: \"{include_pattern}\")"
            
            header_text = f"Found {match_count} {match_term} for pattern \"{pattern}\" {search_location_description}{filter_description}"
            
            if search_truncated:
                header_text += f" (showing first {match_count} of {total_matches_found}+ total matches)"
            
            llm_content = f"{header_text}:\n---\n"
            
            # Define maximum line length before truncation
            MAX_LINE_LENGTH = 1000
            
            for file_path, file_matches in matches_by_file.items():
                try:
                    relative_file_path = os.path.relpath(file_path, self.working_dir)
                except ValueError:
                    relative_file_path = file_path
                llm_content += f"File: {relative_file_path}\n"
                for match in file_matches:
                    trimmed_line = match["content"].strip()
                    # Truncate long lines to prevent context overflow
                    if len(trimmed_line) > MAX_LINE_LENGTH:
                        trimmed_line = trimmed_line[:MAX_LINE_LENGTH] + f" ... (truncated, line was {len(trimmed_line)} characters)"
                    llm_content += f"L{match['line']}: {trimmed_line}\n"
                llm_content += "---\n"
            
            # Add truncation guidance if results were limited
            if search_truncated:
                llm_content += f"""
WARNING: Results truncated to prevent context overflow. To see more results:
- Use a more specific pattern to reduce matches
- Add file filters with the 'include' parameter (e.g., "*.js", "src/**")
- Specify a narrower 'path' to search in a subdirectory
- Increase 'maxResults' parameter if you need more matches (current: {max_results})"""
            
            display_text = f"Found {match_count} {match_term}"
            if search_truncated:
                display_text += f" (truncated from {total_matches_found}+)"
            
            return {
                "llmContent": llm_content.strip(),
                "returnDisplay": display_text
            }
            
        except Exception as e:
            return {
                "llmContent": f"Error during grep search operation: {str(e)}",
                "returnDisplay": f"Error: An unexpected error occurred. {str(e)}"
            }