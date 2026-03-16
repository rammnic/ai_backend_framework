"""
BaseNode - Abstract base class for all pipeline nodes
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, AsyncGenerator
from datetime import datetime

from .context import Context


class BaseNode(ABC):
    """
    Abstract base class for all nodes in the pipeline.
    
    Each node represents a single atomic operation:
    - Input: Reads from Context
    - Processing: Performs the operation
    - Output: Writes to Context
    
    Attributes:
        name: Unique name of the node
        config: Configuration dictionary for the node
        next_node: ID of the next node to execute (for branching)
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.name = name or self.__class__.__name__
        self.config = config or {}
        self.next_node: Optional[str] = None
    
    @abstractmethod
    async def run(self, context: Context) -> Context:
        """
        Execute the node's logic.
        
        Args:
            context: The pipeline context containing all data
            
        Returns:
            Modified context with node's output
        """
        raise NotImplementedError
    
    async def execute(self, context: Context) -> Context:
        """
        Execute the node with logging and error handling.
        
        This method wraps run() with:
        - Start/end time logging
        - Error handling
        - Status tracking
        
        Args:
            context: The pipeline context
            
        Returns:
            Modified context
        """
        started_at = datetime.now().isoformat()
        
        try:
            result = await self.run(context)
            context.add_log(
                node_name=self.name,
                status="success",
                started_at=started_at,
                details={"config": self.config},
            )
            return result
        except Exception as e:
            context.add_log(
                node_name=self.name,
                status="error",
                started_at=started_at,
                error=str(e),
                details={"config": self.config},
            )
            raise
    
    async def stream(self, context: Context) -> AsyncGenerator[Context, None]:
        """
        Execute the node with streaming support.
        
        Override this method for nodes that support streaming output
        (e.g., LLM nodes that stream tokens).
        
        Args:
            context: The pipeline context
            
        Yields:
            Context updates as they become available
        """
        # Default: just execute and yield once
        result = await self.execute(context)
        yield result
    
    def set_next(self, node_id: str) -> "BaseNode":
        """
        Set the next node to execute.
        
        Used for branching logic (ConditionNode).
        
        Args:
            node_id: ID of the next node
            
        Returns:
            Self for chaining
        """
        self.next_node = node_id
        return self
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self.config.get(key, default)
    
    def set_config(self, key: str, value: Any) -> None:
        """Set configuration value"""
        self.config[key] = value
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}')"


class NodeResult:
    """
    Result of a node execution.
    
    Contains the output data and metadata about the execution.
    """
    
    def __init__(
        self,
        success: bool,
        output: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        next_node: Optional[str] = None,
    ):
        self.success = success
        self.output = output or {}
        self.error = error
        self.next_node = next_node
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "next_node": self.next_node,
        }