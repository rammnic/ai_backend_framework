"""
Pipeline configuration schema for validation
"""

from typing import Any, Dict, List, Optional
import re


# JSON Schema for pipeline configuration
PIPELINE_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Pipeline Configuration",
    "description": "Schema for AI Flow Engine pipeline configuration",
    "type": "object",
    "required": ["name", "nodes"],
    "properties": {
        "name": {
            "type": "string",
            "description": "Unique pipeline identifier",
            "minLength": 1,
        },
        "description": {
            "type": "string",
            "description": "Pipeline description",
        },
        "version": {
            "type": "string",
            "description": "Pipeline version",
            "pattern": r"^\d+\.\d+\.\d+$",
        },
        "metadata": {
            "type": "object",
            "description": "Additional pipeline metadata",
        },
        "config": {
            "type": "object",
            "description": "Default configuration for all nodes",
        },
        "nodes": {
            "type": "array",
            "description": "List of pipeline nodes",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["type"],
                "properties": {
                    "type": {
                        "type": "string",
                        "description": "Node type (e.g., LLMNode, ConditionNode)",
                    },
                    "name": {
                        "type": "string",
                        "description": "Unique node name within pipeline",
                    },
                    "config": {
                        "type": "object",
                        "description": "Node-specific configuration",
                    },
                    "next_node": {
                        "type": "string",
                        "description": "Next node to execute (for branching)",
                    },
                },
            },
        },
    },
}

# Node-specific schemas
NODE_SCHEMAS = {
    "LLMNode": {
        "required": [],
        "properties": {
            "model": {"type": "string"},
            "prompt": {"type": "string"},
            "input_key": {"type": "string"},
            "output_key": {"type": "string"},
            "temperature": {"type": "number", "minimum": 0, "maximum": 2},
            "max_tokens": {"type": "integer", "minimum": 1},
            "streaming": {"type": "boolean"},
            "include_history": {"type": "boolean"},
        },
    },
    "PromptNode": {
        "required": [],
        "properties": {
            "template": {"type": "string"},
            "template_key": {"type": "string"},
            "variables": {"type": "object"},
            "output_key": {"type": "string"},
        },
    },
    "ConditionNode": {
        "required": ["condition", "on_true", "on_false"],
        "properties": {
            "condition": {
                "oneOf": [
                    {"type": "object"},
                    {"type": "string"},
                ]
            },
            "on_true": {"type": "string"},
            "on_false": {"type": "string"},
            "output_key": {"type": "string"},
        },
    },
    "WebSearchNode": {
        "required": [],
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 50},
            "provider": {"type": "string", "enum": ["duckduckgo", "serpapi"]},
            "input_key": {"type": "string"},
            "output_key": {"type": "string"},
        },
    },
    "ImageAnalysisNode": {
        "required": [],
        "properties": {
            "model": {"type": "string"},
            "prompt": {"type": "string"},
            "image_path": {"type": "string"},
            "image_url": {"type": "string"},
            "input_key": {"type": "string"},
            "output_key": {"type": "string"},
            "max_tokens": {"type": "integer", "minimum": 1},
        },
    },
    "SwitchNode": {
        "required": ["key", "cases"],
        "properties": {
            "key": {"type": "string"},
            "cases": {"type": "object"},
            "default": {"type": "string"},
        },
    },
}


class ValidationError(Exception):
    """Validation error exception"""
    
    def __init__(self, message: str, path: Optional[str] = None):
        self.message = message
        self.path = path
        super().__init__(f"{path}: {message}" if path else message)


def validate_type(value: Any, expected_type: str, path: str) -> None:
    """Validate value type"""
    type_checks = {
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
    }
    
    if expected_type not in type_checks:
        return
    
    if not type_checks[expected_type](value):
        raise ValidationError(f"Expected {expected_type}, got {type(value).__name__}", path)


def validate_min_max(value: Any, schema: Dict, path: str) -> None:
    """Validate minimum/maximum constraints"""
    if "minimum" in schema and value < schema["minimum"]:
        raise ValidationError(f"Value {value} is below minimum {schema['minimum']}", path)
    if "maximum" in schema and value > schema["maximum"]:
        raise ValidationError(f"Value {value} exceeds maximum {schema['maximum']}", path)
    if "minLength" in schema and len(str(value)) < schema["minLength"]:
        raise ValidationError(f"Length {len(value)} is below minimum {schema['minLength']}", path)
    if "maxItems" in schema and len(value) > schema["maxItems"]:
        raise ValidationError(f"Items count {len(value)} exceeds maximum {schema['maxItems']}", path)


def validate_enum(value: Any, enum_values: List, path: str) -> None:
    """Validate enum constraint"""
    if value not in enum_values:
        raise ValidationError(f"Value '{value}' not in allowed values: {enum_values}", path)


def validate_pattern(value: str, pattern: str, path: str) -> None:
    """Validate regex pattern"""
    if not re.match(pattern, value):
        raise ValidationError(f"Value '{value}' does not match pattern {pattern}", path)


def validate_node_config(node: Dict, path: str) -> None:
    """Validate a single node configuration"""
    node_type = node.get("type")
    
    if not node_type:
        raise ValidationError("Node must have 'type' field", path)
    
    # Check if node type is known
    if node_type not in NODE_SCHEMAS:
        # Allow unknown node types but warn
        return
    
    schema = NODE_SCHEMAS[node_type]
    config = node.get("config", {})
    
    # Check required fields
    for required in schema.get("required", []):
        if required not in config:
            raise ValidationError(f"Missing required field: {required}", f"{path}.config")
    
    # Validate config properties
    for key, value in config.items():
        if key in schema.get("properties", {}):
            prop_schema = schema["properties"][key]
            
            validate_type(value, prop_schema.get("type"), f"{path}.config.{key}")
            
            if prop_schema.get("type") in ("integer", "number"):
                validate_min_max(value, prop_schema, f"{path}.config.{key}")
            
            if "enum" in prop_schema:
                validate_enum(value, prop_schema["enum"], f"{path}.config.{key}")


def validate_pipeline_config(config: Dict) -> List[str]:
    """
    Validate pipeline configuration.
    
    Args:
        config: Pipeline configuration dictionary
        
    Returns:
        List of validation error messages (empty if valid)
        
    Raises:
        ValidationError: If validation fails
    """
    errors = []
    
    # Check required fields
    if "name" not in config:
        errors.append("Pipeline must have 'name' field")
    
    if "nodes" not in config:
        errors.append("Pipeline must have 'nodes' field")
    elif not isinstance(config.get("nodes"), list):
        errors.append("'nodes' must be an array")
    elif len(config.get("nodes", [])) == 0:
        errors.append("'nodes' array cannot be empty")
    
    # Validate nodes
    for i, node in enumerate(config.get("nodes", [])):
        try:
            validate_node_config(node, f"nodes[{i}]")
        except ValidationError as e:
            errors.append(str(e))
    
    # Validate node names are unique
    node_names = []
    for i, node in enumerate(config.get("nodes", [])):
        name = node.get("name") or node.get("type", f"node_{i}")
        if name in node_names:
            errors.append(f"Duplicate node name: {name}")
        node_names.append(name)
    
    # Validate next_node references
    for i, node in enumerate(config.get("nodes", [])):
        next_node = node.get("next_node")
        if next_node and next_node not in node_names:
            errors.append(f"nodes[{i}]: next_node '{next_node}' references unknown node")
    
    if errors:
        raise ValidationError("\n".join(errors))
    
    return errors


def get_schema() -> Dict:
    """Get the full pipeline schema"""
    return PIPELINE_SCHEMA.copy()