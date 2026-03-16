"""
ParallelNode - Node for parallel execution of multiple nodes
"""

from typing import Any, Dict, List, Optional
import asyncio

from ..core.base_node import BaseNode
from ..core.context import Context


class ParallelNode(BaseNode):
    """
    Node for executing multiple nodes in parallel.
    
    Uses asyncio.gather() to run nodes concurrently.
    
    Configuration:
        nodes: List of node instances to execute in parallel
        node_names: List of node names to execute (reference by name in pipeline)
        output_key: Context key to store results dict (default: "parallel_results")
        fail_fast: Stop on first error (default: False)
    
    Example:
        ParallelNode(
            node_names=["fetch_weather", "fetch_news", "fetch_stocks"],
            output_key="all_results"
        )
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        *,
        nodes: Optional[List[BaseNode]] = None,
        node_names: Optional[List[str]] = None,
        output_key: str = "parallel_results",
        fail_fast: bool = False,
    ):
        super().__init__(name, config)
        
        self.nodes = self.get_config("nodes", nodes) or []
        self.node_names = self.get_config("node_names", node_names) or []
        self.output_key = self.get_config("output_key", output_key)
        self.fail_fast = self.get_config("fail_fast", fail_fast)
        
        self._pipeline = None
    
    def set_pipeline(self, pipeline) -> "ParallelNode":
        """Set pipeline reference for node lookup"""
        self._pipeline = pipeline
        return self
    
    async def _execute_node(self, node: BaseNode, context: Context) -> tuple:
        """Execute a single node and return (name, result)"""
        try:
            result = await node.execute(context)
            return (node.name, result, None)
        except Exception as e:
            if self.fail_fast:
                raise
            return (node.name, None, str(e))
    
    async def run(self, context: Context) -> Context:
        """Execute all nodes in parallel"""
        # Get nodes to execute
        nodes_to_execute = list(self.nodes)
        
        # Add nodes by name if specified
        if self.node_names and self._pipeline:
            for node_name in self.node_names:
                node = self._pipeline.get_node(node_name)
                if node:
                    nodes_to_execute.append(node)
                else:
                    raise ValueError(f"Node '{node_name}' not found in pipeline")
        
        if not nodes_to_execute:
            raise ValueError("No nodes to execute in parallel")
        
        # Create tasks for parallel execution
        tasks = [
            self._execute_node(node, context.copy() if not self.fail_fast else context)
            for node in nodes_to_execute
        ]
        
        # Execute all tasks concurrently
        if self.fail_fast:
            # Use first_completed to stop on first error
            results = await asyncio.gather(*tasks, return_exceptions=False)
        else:
            # Use gather with return_exceptions to collect all results
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        output = {}
        errors = {}
        
        for i, result in enumerate(results):
            node_name = nodes_to_execute[i].name
            
            if isinstance(result, Exception):
                errors[node_name] = str(result)
                output[node_name] = None
            else:
                name, ctx, error = result
                if error:
                    errors[node_name] = error
                    output[node_name] = None
                else:
                    output[node_name] = ctx
        
        # Store results in context
        context.set(self.output_key, output)
        
        if errors:
            context.set(f"{self.output_key}_errors", errors)
        
        # Log execution
        context.add_log(
            node_name=self.name,
            status="success" if not errors else "partial",
            started_at=context.metadata.get("started_at", ""),
            details={
                "nodes_count": len(nodes_to_execute),
                "successful": len(output) - len(errors),
                "failed": len(errors),
            },
        )
        
        return context
    
    def __repr__(self) -> str:
        return f"ParallelNode(name='{self.name}', nodes={len(self.nodes) + len(self.node_names)})"


class MapNode(BaseNode):
    """
    Node for mapping a function over a collection in parallel.
    
    Similar to ForLoopNode but executes in parallel.
    
    Configuration:
        items_key: Context key containing the list to iterate over
        callback: Async function to apply to each item
        output_key: Context key to store results list (default: "map_results")
        max_concurrency: Maximum parallel executions (default: 10)
    
    Example:
        MapNode(
            items_key="urls",
            callback=async_fetch_url,
            max_concurrency=5
        )
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        *,
        items_key: str = "items",
        callback: Optional[callable] = None,
        output_key: str = "map_results",
        max_concurrency: int = 10,
    ):
        super().__init__(name, config)
        
        self.items_key = self.get_config("items_key", items_key)
        self.callback = self.get_config("callback", callback)
        self.output_key = self.get_config("output_key", output_key)
        self.max_concurrency = self.get_config("max_concurrency", max_concurrency)
    
    async def run(self, context: Context) -> Context:
        """Execute callback for each item in parallel"""
        items = context.get(self.items_key)
        
        if items is None:
            raise ValueError(f"No items found at key: {self.items_key}")
        
        if not isinstance(items, (list, tuple, set)):
            raise ValueError(f"Items must be a list, got: {type(items)}")
        
        if not self.callback:
            raise ValueError("No callback provided for MapNode")
        
        # Use semaphore to limit concurrency
        semaphore = asyncio.Semaphore(self.max_concurrency)
        
        async def bounded_callback(item):
            async with semaphore:
                return await self.callback(item, context)
        
        # Execute all in parallel with concurrency limit
        results = await asyncio.gather(
            *[bounded_callback(item) for item in items],
            return_exceptions=True
        )
        
        # Filter out exceptions if any
        output = []
        errors = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                errors.append({"index": i, "error": str(result)})
                output.append(None)
            else:
                output.append(result)
        
        # Store results
        context.set(self.output_key, output)
        
        if errors:
            context.set(f"{self.output_key}_errors", errors)
        
        # Log execution
        context.add_log(
            node_name=self.name,
            status="success" if not errors else "partial",
            started_at=context.metadata.get("started_at", ""),
            details={
                "items_count": len(items),
                "successful": len(output) - len(errors),
                "failed": len(errors),
            },
        )
        
        return context
    
    def __repr__(self) -> str:
        return f"MapNode(name='{self.name}', items_key='{self.items_key}')"