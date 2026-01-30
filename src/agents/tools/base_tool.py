"""
Enhanced base tool class for Qwen Code Python implementation with support for tool kinds, validation, and confirmation.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from .tool_types import ToolKind, ToolConfirmationDetails
import json


class BaseTool(ABC):
    """Enhanced abstract base class for all tools with support for kinds, validation, and confirmation."""
    
    def __init__(self, name: str, description: str, parameters: Dict[str, Any], kind: ToolKind = ToolKind.OTHER):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.kind = kind
        
    def get_schema(self) -> Dict[str, Any]:
        """Get the schema for this tool."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }
        
    def validate_params(self, params: Dict[str, Any]) -> Optional[str]:
        """Validate parameters for this tool.
        
        Returns an error message if validation fails, None if successful.
        """
        # Check for required parameters
        required_params = self.parameters.get("required", [])
        for param in required_params:
            if param not in params:
                return f"Missing required parameter: {param}"
                
        # Additional validation can be implemented by subclasses
        return None
        
    def get_description(self, params: Dict[str, Any]) -> str:
        """Get a human-readable description of what this tool will do."""
        return f"Executing {self.name} with parameters: {params}"
        
    def should_confirm_execute(self, params: Dict[str, Any]) -> Optional[ToolConfirmationDetails]:
        """Check if tool execution should be confirmed.
        
        Returns confirmation details or None if no confirmation is needed.
        """
        return None
        
    @abstractmethod
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the tool with the given parameters.
        
        Returns a dictionary with:
        - llmContent: Content to send back to the LLM
        - returnDisplay: Content to display to the user
        """
        pass