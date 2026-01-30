"""
Enhanced tool registry for Qwen Code Python implementation with support for tool kinds, validation, and confirmation.
"""
from typing import Dict, Any, List, Optional, TYPE_CHECKING
import os

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if TYPE_CHECKING:
    from tools.base_tool import BaseTool

from tools import ToolKind, ToolConfirmationDetails



class ToolRegistry:
    """Enhanced registry for managing and executing tools with support for kinds, validation, and confirmation."""
    
    def __init__(self):
        self.tools: Dict[str, 'BaseTool'] = {}
        self.allowlist: Dict[str, bool] = {}  # For tracking approved tools
        
    def register_tool(self, tool: 'BaseTool'):
        """Register a tool in the registry."""
        self.tools[tool.name] = tool
        
    def get_tool(self, name: str) -> Optional['BaseTool']:
        """Get a tool by name."""
        return self.tools.get(name)
        
    def get_all_tools(self) -> List['BaseTool']:
        """Get all registered tools."""
        return list(self.tools.values())
        
    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Get schemas for all registered tools."""
        schemas = []
        for tool in self.tools.values():
            schema = tool.get_schema()
            # Add kind if available
            if hasattr(tool, 'kind') and tool.kind:
                schema["kind"] = tool.kind.value
            schemas.append(schema)
        return schemas
        
    def get_tools_by_kind(self, kind: ToolKind) -> List['BaseTool']:
        """Get tools filtered by kind."""
        return [tool for tool in self.tools.values() if hasattr(tool, 'kind') and tool.kind == kind]
        
    def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool by name with given parameters."""
        tool = self.get_tool(tool_name)
        if not tool:
            return {
                "llmContent": f"Error: Unknown tool '{tool_name}'",
                "returnDisplay": f"Error: Unknown tool '{tool_name}'"
            }
            
        # Validate parameters if validator is available
        if hasattr(tool, 'validate_params'):
            validation_error = tool.validate_params(params)
            if validation_error:
                return {
                    "llmContent": f"Error: Invalid parameters for tool '{tool_name}': {validation_error}",
                    "returnDisplay": f"Error: Invalid parameters: {validation_error}"
                }
            
        try:
            return tool.execute(params)
        except Exception as e:
            return {
                "llmContent": f"Error executing tool {tool_name}: {str(e)}",
                "returnDisplay": f"Error: {str(e)}"
            }
            
    def should_confirm_execute(self, tool_name: str, params: Dict[str, Any]) -> Optional[ToolConfirmationDetails]:
        """Check if tool execution should be confirmed."""
        tool = self.get_tool(tool_name)
        if not tool:
            return None
            
        if hasattr(tool, 'should_confirm_execute'):
            return tool.should_confirm_execute(params)
        return None
    
    def is_tool_approved(self, tool_name: str) -> bool:
        """Check if a tool is in the allowlist."""
        return self.allowlist.get(tool_name, False)
    
    def approve_tool(self, tool_name: str):
        """Add a tool to the allowlist."""
        self.allowlist[tool_name] = True