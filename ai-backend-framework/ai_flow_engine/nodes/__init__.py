"""
Nodes module - Ready-to-use pipeline nodes
"""

from .llm_node import LLMNode
from .prompt_node import PromptNode
from .condition_node import ConditionNode, SwitchNode, EndNode
from .web_search_node import WebSearchNode
from .image_analysis_node import ImageAnalysisNode, ImageGenerationNode
from .loop_node import ForLoopNode, WhileLoopNode
from .parallel_node import ParallelNode, MapNode
from .json_parse_node import JsonParseNode, JsonTransformNode, ExtractCourseMetadataNode

# Node registry for pipeline deserialization
NODE_REGISTRY = {
    "LLMNode": LLMNode,
    "PromptNode": PromptNode,
    "ConditionNode": ConditionNode,
    "SwitchNode": SwitchNode,
    "EndNode": EndNode,
    "WebSearchNode": WebSearchNode,
    "ImageAnalysisNode": ImageAnalysisNode,
    "ImageGenerationNode": ImageGenerationNode,
    "ForLoopNode": ForLoopNode,
    "WhileLoopNode": WhileLoopNode,
    "ParallelNode": ParallelNode,
    "MapNode": MapNode,
    "JsonParseNode": JsonParseNode,
    "JsonTransformNode": JsonTransformNode,
    "ExtractCourseMetadataNode": ExtractCourseMetadataNode,
}

__all__ = [
    "LLMNode",
    "PromptNode",
    "ConditionNode",
    "SwitchNode",
    "EndNode",
    "WebSearchNode",
    "ImageAnalysisNode",
    "ImageGenerationNode",
    "ForLoopNode",
    "WhileLoopNode",
    "ParallelNode",
    "MapNode",
    "JsonParseNode",
    "JsonTransformNode",
    "ExtractCourseMetadataNode",
    "NODE_REGISTRY",
]
