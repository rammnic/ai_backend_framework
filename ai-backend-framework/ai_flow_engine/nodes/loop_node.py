"""
LoopNode - Node for iterating over collections
"""

from typing import Any, Dict, List, Optional, Callable

from ..core.base_node import BaseNode
from ..core.context import Context


class ForLoopNode(BaseNode):
    """
    Node for iterating over a collection of items.
    
    Executes a node or callback for each item in a list.
    
    Configuration:
        items_key: Context key containing the list to iterate over
        item_key: Key to store each item as during iteration (default: "item")
        node_name: Name of the node to execute for each item (reference by name)
        callback: Optional async function(item, context) for custom logic
        output_key: Context key to store results list (default: "loop_results")
        index_key: Key to store current index (default: "loop_index")
    
    Example:
        ForLoopNode(
            items_key="urls",
            item_key="url",
            node_name="process_url",
            output_key="processed_results"
        )
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        *,
        items_key: str = "items",
        item_key: str = "item",
        node_name: Optional[str] = None,
        callback: Optional[Callable[[Any, Context], Any]] = None,
        output_key: str = "loop_results",
        index_key: str = "loop_index",
    ):
        super().__init__(name, config)
        
        self.items_key = self.get_config("items_key", items_key)
        self.item_key = self.get_config("item_key", item_key)
        self.node_name = self.get_config("node_name", node_name)
        self.callback = self.get_config("callback", callback)
        self.output_key = self.get_config("output_key", output_key)
        self.index_key = self.get_config("index_key", index_key)
        
        # Store reference to pipeline for node lookup
        self._pipeline = None
    
    def set_pipeline(self, pipeline) -> "ForLoopNode":
        """Set pipeline reference for node lookup"""
        self._pipeline = pipeline
        return self
    
    async def run(self, context: Context) -> Context:
        """Execute the loop"""
        # Get items from context
        items = context.get(self.items_key)
        
        if items is None:
            raise ValueError(f"No items found at key: {self.items_key}")
        
        if not isinstance(items, (list, tuple, set)):
            raise ValueError(f"Items must be a list, got: {type(items)}")
        
        if len(items) == 0:
            context.set(self.output_key, [])
            return context
        
        results = []
        
        # Execute for each item
        for index, item in enumerate(items):
            # Store current item and index in context
            context.set(self.item_key, item)
            context.set(self.index_key, index)
            
            if self.callback:
                # Use callback function
                result = await self.callback(item, context)
                results.append(result)
            elif self.node_name and self._pipeline:
                # Execute named node from pipeline
                node = self._pipeline.get_node(self.node_name)
                if node:
                    context = await node.execute(context)
                    # Get result from node's output key
                    result = context.get(node.output_key if hasattr(node, 'output_key') else None)
                    results.append(result)
                else:
                    raise ValueError(f"Node '{self.node_name}' not found in pipeline")
            else:
                # No operation, just store item
                results.append(item)
        
        # Store results
        context.set(self.output_key, results)
        
        # Clean up temporary keys
        if self.item_key in context.data:
            del context.data[self.item_key]
        if self.index_key in context.data:
            del context.data[self.index_key]
        
        # Log execution
        context.add_log(
            node_name=self.name,
            status="success",
            started_at=context.metadata.get("started_at", ""),
            details={
                "items_count": len(items),
                "results_count": len(results),
            },
        )
        
        return context
    
    def __repr__(self) -> str:
        return f"ForLoopNode(name='{self.name}', items_key='{self.items_key}', node_name='{self.node_name}')"


class WhileLoopNode(BaseNode):
    """
    Node for executing while a condition is true.
    
    Note: Use with caution to avoid infinite loops.
    Maximum iterations controlled by max_iterations.
    
    Configuration:
        condition_key: Context key containing boolean condition
        node_name: Name of the node to execute while condition is true
        max_iterations: Maximum number of iterations (default: 100)
        output_key: Context key to store iteration count
    
    Example:
        WhileLoopNode(
            condition_key="has_more",
            node_name="fetch_more",
            max_iterations=10
        )
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        *,
        condition_key: str = "condition",
        node_name: Optional[str] = None,
        max_iterations: int = 100,
        output_key: str = "while_iterations",
    ):
        super().__init__(name, config)
        
        self.condition_key = self.get_config("condition_key", condition_key)
        self.node_name = self.get_config("node_name", node_name)
        self.max_iterations = self.get_config("max_iterations", max_iterations)
        self.output_key = self.get_config("output_key", output_key)
        
        self._pipeline = None
    
    def set_pipeline(self, pipeline) -> "WhileLoopNode":
        """Set pipeline reference for node lookup"""
        self._pipeline = pipeline
        return self
    
    async def run(self, context: Context) -> Context:
        """Execute while condition is true"""
        iteration = 0
        
        while iteration < self.max_iterations:
            # Check condition
            condition = context.get(self.condition_key)
            
            if not condition:
                break
            
            # Execute the node
            if self.node_name and self._pipeline:
                node = self._pipeline.get_node(self.node_name)
                if node:
                    context = await node.execute(context)
                else:
                    raise ValueError(f"Node '{self.node_name}' not found in pipeline")
            
            iteration += 1
        
        # Store iteration count
        context.set(self.output_key, iteration)
        
        # Log execution
        context.add_log(
            node_name=self.name,
            status="success",
            started_at=context.metadata.get("started_at", ""),
            details={
                "iterations": iteration,
                "max_iterations": self.max_iterations,
            },
        )
        
        return context
    
    def __repr__(self) -> str:
        return f"WhileLoopNode(name='{self.name}', condition_key='{self.condition_key}')"