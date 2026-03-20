"""
JsonParseNode - Node for parsing JSON from text/markdown blocks
Uses json_repair as primary method for robust parsing.
"""

import json
import re
from typing import Any, Dict, Optional

try:
    from json_repair import repair_json
except ImportError:
    repair_json = None

from ..core.base_node import BaseNode
from ..core.context import Context


class JsonParseNode(BaseNode):
    """
    Node that parses JSON from text that may contain markdown code blocks.
    
    Uses json_repair library as primary method for robust parsing.
    Falls back to manual extraction if repair fails.
    
    Configuration:
        input_key: Key in context containing the text to parse (required)
        output_key: Key to store parsed JSON in context (default: "parsed_json")
        default_on_error: Default value to use if parsing fails (optional)
    
    Example:
        Input: "```json\n[{\"title\": \"Topic 1\"}]\n```"
        Output: [{"title": "Topic 1"}]
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(name or "JsonParseNode", config)
    
    def _extract_json_content(self, text: str) -> str:
        """
        Extract JSON content from text, removing markdown code blocks.
        """
        if not text:
            return text
        
        # Try to find JSON inside fenced code blocks
        json_block_pattern = r"```(?:json)?\s*(.*?)\s*```"
        matches = re.findall(json_block_pattern, text, re.DOTALL | re.IGNORECASE)
        if matches:
            return matches[0].strip()
        
        # If no code block found, return the original text
        return text.strip()
    
    async def run(self, context: Context) -> Context:
        """
        Execute JSON parsing.
        
        Reads from context[input_key], parses JSON, writes to context[output_key].
        """
        input_key = self.get_config("input_key")
        output_key = self.get_config("output_key", "parsed_json")
        default_on_error = self.get_config("default_on_error", None)
        
        if not input_key:
            raise ValueError("JsonParseNode requires 'input_key' in config")
        
        input_text = context.get(input_key)
        
        # Handle already-parsed JSON (when LLM returns dict in json_mode)
        if isinstance(input_text, (dict, list)):
            context.set(output_key, input_text)
            return context
        
        if input_text is None:
            if default_on_error is not None:
                context.set(output_key, default_on_error)
            else:
                raise ValueError(f"Input key '{input_key}' not found in context")
            return context
        
        try:
            # Step 1: Extract content from markdown code blocks
            json_text = self._extract_json_content(str(input_text))
            
            # Step 2: Try direct JSON parse first
            try:
                parsed = json.loads(json_text)
                context.set(output_key, parsed)
                return context
            except json.JSONDecodeError:
                pass
            
            # Step 3: Use json_repair for robust parsing
            if repair_json is not None:
                try:
                    repaired = repair_json(json_text)
                    parsed = json.loads(repaired)
                    context.set(output_key, parsed)
                    return context
                except (json.JSONDecodeError, TypeError):
                    pass
            
            # Step 4: Try to find JSON array/object substring
            array_match = re.search(r'\[[\s\S]*\]', json_text)
            if array_match:
                try:
                    parsed = json.loads(array_match.group(0))
                    context.set(output_key, parsed)
                    return context
                except json.JSONDecodeError:
                    pass
            
            object_match = re.search(r'\{[\s\S]*\}', json_text)
            if object_match:
                try:
                    parsed = json.loads(object_match.group(0))
                    context.set(output_key, parsed)
                    return context
                except json.JSONDecodeError:
                    pass
            
            # If all else fails, return the extracted text as-is
            if default_on_error is not None:
                context.set(output_key, default_on_error)
            else:
                raise ValueError(
                    f"Failed to parse JSON from '{input_key}'. "
                    f"Preview: {json_text[:200]!r}"
                )
                
        except Exception as e:
            if default_on_error is not None:
                context.set(output_key, default_on_error)
            else:
                raise ValueError(f"Failed to parse JSON from '{input_key}': {str(e)}")
        
        return context


class JsonTransformNode(BaseNode):
    """
    Node that transforms parsed JSON into structure format for LMS.
    
    Converts from:
    {"topics": [{"title": "Topic", "description": "...", "children": [...]}]}
    
    To:
    [{"id": "uuid", "title": "Topic", "type": "topic", "children": [...]}]
    
    Configuration:
        input_key: Key in context containing the JSON array (required)
        output_key: Key to store transformed structure (default: "structure")
        default_type: Type to use for nodes (default: "topic")
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(name or "JsonTransformNode", config)
    
    def _transform_item(self, item: Dict[str, Any], default_type: str = "topic") -> Dict[str, Any]:
        """Transform a single item to include id and type."""
        import uuid
        
        result = {
            "id": str(uuid.uuid4()),
            "title": item.get("title", "Untitled"),
            "type": item.get("type", default_type),
        }
        
        if "description" in item:
            result["description"] = item["description"]
        
        if "children" in item and isinstance(item["children"], list):
            result["children"] = [
                self._transform_item(child, "theory") 
                for child in item["children"]
            ]
        
        return result

    async def run(self, context: Context) -> Context:
        """Execute JSON transformation."""
        input_key = self.get_config("input_key")
        output_key = self.get_config("output_key", "structure")
        default_type = self.get_config("default_type", "topic")

        if not input_key:
            raise ValueError("JsonTransformNode requires 'input_key' in config")

        input_data = context.get(input_key)
        if input_data is None:
            raise ValueError(f"Input key '{input_key}' not found in context")
        
        # If input is a string, try to parse it
        if isinstance(input_data, str):
            try:
                input_data = json.loads(input_data)
            except json.JSONDecodeError:
                if repair_json is not None:
                    input_data = json.loads(repair_json(input_data))
                else:
                    raise ValueError(f"Cannot parse string as JSON: {input_data[:200]!r}")

        # Extract topics array from various possible structures
        def extract_topics(data: Any) -> list:
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                # Try common keys
                for key in ("topics", "structure", "items", "outline"):
                    if key in data and isinstance(data[key], list):
                        return data[key]
                # If dict has title/children, wrap in list
                if "title" in data or "children" in data:
                    return [data]
            return []

        topics = extract_topics(input_data)
        
        if not topics:
            raise ValueError(
                f"Cannot extract topics array from input. "
                f"Keys: {list(input_data.keys()) if isinstance(input_data, dict) else type(input_data).__name__}"
            )

        structure = [self._transform_item(item, default_type) for item in topics]
        context.set(output_key, structure)
        return context


class ExtractCourseMetadataNode(BaseNode):
    """
    Node that extracts course title and description from the first topic.
    
    Uses the first item in the structure array to set course_title and course_description.
    
    Configuration:
        input_key: Key in context containing the structure array (required)
        title_output_key: Key to store course title (default: "course_title")
        description_output_key: Key to store course description (default: "course_description")
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(name or "ExtractCourseMetadataNode", config)
    
    async def run(self, context: Context) -> Context:
        """Extract course metadata from structure."""
        input_key = self.get_config("input_key", "structure")
        title_output_key = self.get_config("title_output_key", "course_title")
        description_output_key = self.get_config("description_output_key", "course_description")
        
        structure = context.get(input_key)
        
        if structure and isinstance(structure, list) and len(structure) > 0:
            first_topic = structure[0]
            context.set(title_output_key, first_topic.get("title", "Untitled Course"))
            context.set(description_output_key, first_topic.get("description", ""))
        else:
            context.set(title_output_key, "Untitled Course")
            context.set(description_output_key, "")
        
        return context
