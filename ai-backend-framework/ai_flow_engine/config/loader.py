"""
Pipeline loader - Load pipelines from JSON/YAML files
"""

from typing import Any, Dict, List, Optional, Type
import json
import os

import yaml

from ..core.base_node import BaseNode
from ..core.engine import Pipeline
from ..nodes import NODE_REGISTRY
from .schema import validate_pipeline_config


class PipelineLoader:
    """
    Loader for pipeline configurations.
    
    Features:
    - Load from JSON files
    - Load from YAML files
    - Load from dictionaries
    - Support for custom node registry
    - Configuration validation
    """
    
    def __init__(
        self,
        node_registry: Optional[Dict[str, Type[BaseNode]]] = None,
        validate: bool = True,
    ):
        """
        Initialize pipeline loader.
        
        Args:
            node_registry: Custom node registry (defaults to built-in nodes)
            validate: Whether to validate configurations
        """
        self.node_registry = node_registry or NODE_REGISTRY.copy()
        self.validate = validate
    
    def register_node(self, node_type: str, node_class: Type[BaseNode]) -> None:
        """Register a custom node type"""
        self.node_registry[node_type] = node_class
    
    def load_from_dict(self, config: Dict[str, Any]) -> Pipeline:
        """
        Load pipeline from dictionary.
        
        Args:
            config: Pipeline configuration dictionary
            
        Returns:
            Pipeline instance
        """
        if self.validate:
            validate_pipeline_config(config)
        
        return self._build_pipeline(config)
    
    def load_from_json(self, filepath: str) -> Pipeline:
        """
        Load pipeline from JSON file.
        
        Args:
            filepath: Path to JSON file
            
        Returns:
            Pipeline instance
        """
        with open(filepath, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        return self.load_from_dict(config)
    
    def load_from_yaml(self, filepath: str) -> Pipeline:
        """
        Load pipeline from YAML file.
        
        Args:
            filepath: Path to YAML file
            
        Returns:
            Pipeline instance
        """
        with open(filepath, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        return self.load_from_dict(config)
    
    def load_from_file(self, filepath: str) -> Pipeline:
        """
        Load pipeline from file (auto-detect format by extension).
        
        Args:
            filepath: Path to configuration file
            
        Returns:
            Pipeline instance
        """
        ext = os.path.splitext(filepath)[1].lower()
        
        if ext in (".yaml", ".yml"):
            return self.load_from_yaml(filepath)
        elif ext == ".json":
            return self.load_from_json(filepath)
        else:
            raise ValueError(f"Unsupported file format: {ext}")
    
    def load_from_directory(self, directory: str) -> Dict[str, Pipeline]:
        """
        Load all pipelines from a directory.
        
        Args:
            directory: Path to directory containing pipeline files
            
        Returns:
            Dictionary mapping pipeline names to Pipeline instances
        """
        pipelines = {}
        
        for filename in os.listdir(directory):
            filepath = os.path.join(directory, filename)
            
            if os.path.isfile(filepath):
                try:
                    pipeline = self.load_from_file(filepath)
                    pipelines[pipeline.name] = pipeline
                except Exception as e:
                    # Skip invalid files
                    print(f"Warning: Failed to load {filepath}: {e}")
        
        return pipelines
    
    def _build_pipeline(self, config: Dict[str, Any]) -> Pipeline:
        """Build pipeline from configuration"""
        nodes = []
        
        # Get global config
        global_config = config.get("config", {})
        
        for node_data in config.get("nodes", []):
            node = self._build_node(node_data, global_config)
            nodes.append(node)
        
        return Pipeline(
            nodes=nodes,
            name=config.get("name", "unnamed"),
            metadata={
                "description": config.get("description"),
                "version": config.get("version", "0.0.0"),
                **config.get("metadata", {}),
            },
        )
    
    def _build_node(
        self,
        node_data: Dict[str, Any],
        global_config: Dict[str, Any],
    ) -> BaseNode:
        """Build a node from configuration"""
        node_type = node_data.get("type")
        
        if node_type not in self.node_registry:
            raise ValueError(f"Unknown node type: {node_type}")
        
        node_class = self.node_registry[node_type]
        
        # Merge global and node-specific config
        node_config = {**global_config, **node_data.get("config", {})}
        
        # Create node instance
        node = node_class(
            name=node_data.get("name"),
            config=node_config,
        )
        
        # Set next_node if specified
        if node_data.get("next_node"):
            node.set_next(node_data["next_node"])
        
        return node


def load_pipeline(config: Dict[str, Any]) -> Pipeline:
    """
    Quick function to load pipeline from dictionary.
    
    Args:
        config: Pipeline configuration
        
    Returns:
        Pipeline instance
    """
    loader = PipelineLoader()
    return loader.load_from_dict(config)


def load_pipeline_from_file(filepath: str) -> Pipeline:
    """
    Quick function to load pipeline from file.
    
    Args:
        filepath: Path to configuration file
        
    Returns:
        Pipeline instance
    """
    loader = PipelineLoader()
    return loader.load_from_file(filepath)


# Example pipeline configurations
EXAMPLE_PIPELINES = {
    "simple_chat": {
        "name": "simple_chat",
        "description": "Simple chat with LLM",
        "nodes": [
            {
                "type": "LLMNode",
                "name": "chat",
                "config": {
                    "model": "openai/gpt-4o-mini",
                    "include_history": True,
                },
            },
        ],
    },
    "analyze_and_respond": {
        "name": "analyze_and_respond",
        "description": "Analyze input and generate response",
        "nodes": [
            {
                "type": "PromptNode",
                "name": "prepare_prompt",
                "config": {
                    "template": "Analyze the following text and provide insights: {{ user_input }}",
                    "output_key": "analysis_prompt",
                },
            },
            {
                "type": "LLMNode",
                "name": "analyze",
                "config": {
                    "model": "openai/gpt-4o-mini",
                    "input_key": "analysis_prompt",
                    "output_key": "analysis",
                },
            },
        ],
    },
    "search_and_summarize": {
        "name": "search_and_summarize",
        "description": "Web search and summarize results",
        "nodes": [
            {
                "type": "WebSearchNode",
                "name": "search",
                "config": {
                    "max_results": 5,
                    "output_key": "search_results",
                },
            },
            {
                "type": "PromptNode",
                "name": "prepare_summary",
                "config": {
                    "template": "Summarize these search results: {{ search_results }}",
                    "output_key": "summary_prompt",
                },
            },
            {
                "type": "LLMNode",
                "name": "summarize",
                "config": {
                    "model": "openai/gpt-4o-mini",
                    "input_key": "summary_prompt",
                    "output_key": "summary",
                },
            },
        ],
    },
    "conditional_response": {
        "name": "conditional_response",
        "description": "Analyze sentiment and respond accordingly",
        "nodes": [
            {
                "type": "PromptNode",
                "name": "sentiment_prompt",
                "config": {
                    "template": "Analyze the sentiment of this text. Reply with only: positive, negative, or neutral. Text: {{ user_input }}",
                    "output_key": "sentiment_prompt",
                },
            },
            {
                "type": "LLMNode",
                "name": "detect_sentiment",
                "config": {
                    "model": "openai/gpt-4o-mini",
                    "input_key": "sentiment_prompt",
                    "output_key": "sentiment",
                },
            },
            {
                "type": "ConditionNode",
                "name": "check_sentiment",
                "config": {
                    "condition": {"key": "sentiment", "operator": "contains", "value": "positive"},
                    "on_true": "positive_response",
                    "on_false": "negative_response",
                },
            },
            {
                "type": "LLMNode",
                "name": "positive_response",
                "config": {
                    "model": "openai/gpt-4o-mini",
                    "prompt": "Give an encouraging and positive response to: {{ user_input }}",
                    "output_key": "final_response",
                },
            },
            {
                "type": "LLMNode",
                "name": "negative_response",
                "config": {
                    "model": "openai/gpt-4o-mini",
                    "prompt": "Give a helpful and supportive response to: {{ user_input }}",
                    "output_key": "final_response",
                },
            },
        ],
    },
}