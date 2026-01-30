"""
Folder utilities for Qwen Code Python implementation.
"""
import os
from typing import List, Dict, Any

# Common directories to ignore in folder structure display
IGNORED_DIRS = {
    'node_modules', '.next', '.git', '__pycache__', '.venv', 'venv',
    '.DS_Store', '.idea', '.vscode', 'dist', 'build', '.pytest_cache',
    '.egg-info', 'coverage', '.nyc_output'
}

def get_folder_structure(root_path: str, max_depth: int = 3) -> str:
    """Get a textual representation of the folder structure."""
    def _get_structure(path: str, prefix: str = "", is_last: bool = True, depth: int = 0) -> List[str]:
        if depth > max_depth:
            return []
            
        if not os.path.exists(path):
            return []
            
        lines = []
        basename = os.path.basename(path) if path != root_path else "."
        
        # Skip ignored directories
        if basename in IGNORED_DIRS:
            return []
        
        # Add current directory
        if depth > 0:
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{basename}")
            
        # Update prefix for children
        if depth > 0:
            extension = "    " if is_last else "│   "
            child_prefix = prefix + extension
        else:
            child_prefix = ""
            
        # Process children
        try:
            if os.path.isdir(path):
                items = sorted(os.listdir(path))
                dirs = [item for item in items if os.path.isdir(os.path.join(path, item)) and item not in IGNORED_DIRS]
                files = [item for item in items if os.path.isfile(os.path.join(path, item))]
                
                # Combine dirs and files, dirs first
                all_items = dirs + files
                for i, item in enumerate(all_items):
                    item_path = os.path.join(path, item)
                    is_last_item = (i == len(all_items) - 1)
                    lines.extend(_get_structure(item_path, child_prefix, is_last_item, depth + 1))
        except PermissionError:
            lines.append(f"{child_prefix}└── [Permission Denied]")
            
        return lines
        
    structure_lines = _get_structure(root_path)
    return "\n".join(structure_lines)