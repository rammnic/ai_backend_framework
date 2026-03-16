"""
Nodes module - Ready-to-use pipeline nodes
"""

from .llm_node import LLMNode
from .prompt_node import PromptNode
from .condition_node import ConditionNode
from .web_search_node import WebSearchNode
from .image_analysis_node import ImageAnalysisNode

# Node registry for pipeline deserialization
NODE_REGISTRY = {
    "LLMNode": LLMNode,
    "PromptNode": PromptNode,
    "ConditionNode": ConditionNode,
    "WebSearchNode": WebSearchNode,
    "ImageAnalysisNode": ImageAnalysisNode,
}

__all__ = [
    "LLMNode",
    "PromptNode",
    "ConditionNode",
    "WebSearchNode",
    "ImageAnalysisNode",
    "NODE_REGISTRY",
]