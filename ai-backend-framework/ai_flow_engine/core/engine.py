"""
PipelineRunner - Engine for executing pipelines
"""

from typing import Any, Dict, List, Optional, AsyncGenerator, Union
from datetime import datetime
import asyncio

from .context import Context
from .base_node import BaseNode


class Pipeline:
    """
    Pipeline definition containing a sequence of nodes.
    
    Supports:
    - Sequential execution
    - Branching (via ConditionNode)
    - Parallel execution (future)
    """
    
    def __init__(
        self,
        nodes: Optional[List[BaseNode]] = None,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.nodes = nodes or []
        self.name = name or "unnamed_pipeline"
        self.metadata = metadata or {}
        self._node_map: Dict[str, BaseNode] = {}
        
        # Build node map for branching
        for node in self.nodes:
            self._node_map[node.name] = node
    
    def add_node(self, node: BaseNode) -> "Pipeline":
        """Add a node to the pipeline"""
        self.nodes.append(node)
        self._node_map[node.name] = node
        return self
    
    def get_node(self, name: str) -> Optional[BaseNode]:
        """Get node by name"""
        return self._node_map.get(name)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize pipeline to dictionary"""
        return {
            "name": self.name,
            "metadata": self.metadata,
            "nodes": [
                {
                    "type": node.__class__.__name__,
                    "name": node.name,
                    "config": node.config,
                    "next_node": node.next_node,
                }
                for node in self.nodes
            ],
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], node_registry: Dict[str, type]) -> "Pipeline":
        """
        Create pipeline from dictionary.
        
        Args:
            data: Pipeline definition dictionary
            node_registry: Dictionary mapping node type names to classes
            
        Returns:
            Pipeline instance
        """
        nodes = []
        for node_data in data.get("nodes", []):
            node_type = node_data.get("type")
            node_class = node_registry.get(node_type)
            
            if node_class is None:
                raise ValueError(f"Unknown node type: {node_type}")
            
            node = node_class(
                name=node_data.get("name"),
                config=node_data.get("config"),
            )
            
            if node_data.get("next_node"):
                node.set_next(node_data["next_node"])
            
            nodes.append(node)
        
        return cls(
            nodes=nodes,
            name=data.get("name"),
            metadata=data.get("metadata"),
        )


class PipelineRunner:
    """
    Engine for executing pipelines.
    
    Features:
    - Sequential execution
    - Branching support via node.next_node
    - Streaming support
    - Error handling with stop-on-error
    - Execution logging
    """
    
    def __init__(
        self,
        stop_on_error: bool = True,
        max_steps: int = 100,
    ):
        self.stop_on_error = stop_on_error
        self.max_steps = max_steps
    
    async def execute(
        self,
        pipeline: Union[Pipeline, List[BaseNode]],
        context: Optional[Context] = None,
        initial_data: Optional[Dict[str, Any]] = None,
    ) -> Context:
        """
        Execute a pipeline.
        
        Args:
            pipeline: Pipeline instance or list of nodes
            context: Existing context (optional)
            initial_data: Initial data for new context
            
        Returns:
            Final context after all nodes executed
        """
        # Normalize input
        if isinstance(pipeline, list):
            pipeline = Pipeline(nodes=pipeline)
        
        # Create or use context
        if context is None:
            context = Context(data=initial_data or {})
        
        context.metadata["pipeline_name"] = pipeline.name
        context.metadata["started_at"] = datetime.now().isoformat()
        
        # Execute nodes
        step_count = 0
        current_index = 0
        
        while current_index < len(pipeline.nodes) and step_count < self.max_steps:
            node = pipeline.nodes[current_index]
            
            try:
                context = await node.execute(context)
            except Exception as e:
                if self.stop_on_error:
                    context.metadata["finished_at"] = datetime.now().isoformat()
                    context.metadata["status"] = "error"
                    raise
                # Continue to next node on error if stop_on_error is False
                context.add_log(
                    node_name=node.name,
                    status="error",
                    started_at=datetime.now().isoformat(),
                    error=str(e),
                )
            
            # Check for branching
            if node.next_node:
                next_node = pipeline.get_node(node.next_node)
                if next_node:
                    current_index = pipeline.nodes.index(next_node)
                else:
                    raise ValueError(f"Node '{node.next_node}' not found in pipeline")
            else:
                current_index += 1
            
            step_count += 1
        
        context.metadata["finished_at"] = datetime.now().isoformat()
        context.metadata["status"] = "success"
        context.metadata["steps_executed"] = step_count
        
        return context
    
    async def stream(
        self,
        pipeline: Union[Pipeline, List[BaseNode]],
        context: Optional[Context] = None,
        initial_data: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Context, None]:
        """
        Execute a pipeline with streaming support.
        
        Yields context after each node completes.
        For nodes that support streaming, yields incremental updates.
        
        Args:
            pipeline: Pipeline instance or list of nodes
            context: Existing context (optional)
            initial_data: Initial data for new context
            
        Yields:
            Context updates as they become available
        """
        # Normalize input
        if isinstance(pipeline, list):
            pipeline = Pipeline(nodes=pipeline)
        
        # Create or use context
        if context is None:
            context = Context(data=initial_data or {})
        
        context.metadata["pipeline_name"] = pipeline.name
        context.metadata["started_at"] = datetime.now().isoformat()
        
        # Execute nodes with streaming
        step_count = 0
        current_index = 0
        
        while current_index < len(pipeline.nodes) and step_count < self.max_steps:
            node = pipeline.nodes[current_index]
            
            try:
                # Use stream method for nodes that support it
                async for updated_context in node.stream(context):
                    context = updated_context
                    yield context
            except Exception as e:
                if self.stop_on_error:
                    context.metadata["finished_at"] = datetime.now().isoformat()
                    context.metadata["status"] = "error"
                    raise
            
            # Check for branching
            if node.next_node:
                next_node = pipeline.get_node(node.next_node)
                if next_node:
                    current_index = pipeline.nodes.index(next_node)
                else:
                    raise ValueError(f"Node '{node.next_node}' not found in pipeline")
            else:
                current_index += 1
            
            step_count += 1
        
        context.metadata["finished_at"] = datetime.now().isoformat()
        context.metadata["status"] = "success"
        context.metadata["steps_executed"] = step_count


def create_runner(**kwargs) -> PipelineRunner:
    """Factory function to create a PipelineRunner"""
    return PipelineRunner(**kwargs)