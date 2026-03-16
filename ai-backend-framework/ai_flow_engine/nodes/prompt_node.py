"""
PromptNode - Node for prompt template processing
"""

from typing import Any, Dict, Optional
from jinja2 import Template, TemplateError

from ..core.base_node import BaseNode
from ..core.context import Context


class PromptNode(BaseNode):
    """
    Node for processing prompt templates with Jinja2.
    
    Features:
    - Template rendering with context variables
    - Variable substitution from context
    - Conditional template logic
    - Output to context or as LLM input
    
    Configuration:
        template: Jinja2 template string
        template_key: Context key to read template from (alternative to template)
        variables: Dict mapping context keys to template variables
        output_key: Context key to write rendered prompt (default: "prompt")
    
    Example:
        PromptNode(
            template="Analyze this text: {{ text }}. Focus on: {{ focus }}",
            variables={"text": "user_input", "focus": "analysis_focus"},
            output_key="llm_prompt"
        )
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        *,
        template: Optional[str] = None,
        template_key: Optional[str] = None,
        variables: Optional[Dict[str, str]] = None,
        output_key: str = "prompt",
    ):
        super().__init__(name, config)
        
        self.template = self.get_config("template", template)
        self.template_key = self.get_config("template_key", template_key)
        self.variables = self.get_config("variables", variables) or {}
        self.output_key = self.get_config("output_key", output_key)
    
    def _get_template(self, context: Context) -> str:
        """Get template string from config or context"""
        if self.template:
            return self.template
        if self.template_key:
            return context.get(self.template_key, "")
        raise ValueError("No template or template_key provided")
    
    def _build_variables(self, context: Context) -> Dict[str, Any]:
        """Build variables dict from context"""
        result = {}
        
        # Add all context data as variables
        result.update(context.data)
        
        # Map specific keys if configured
        for var_name, context_key in self.variables.items():
            value = context.get(context_key)
            if value is not None:
                result[var_name] = value
        
        return result
    
    async def run(self, context: Context) -> Context:
        """Render the template"""
        template_str = self._get_template(context)
        variables = self._build_variables(context)
        
        try:
            template = Template(template_str)
            rendered = template.render(**variables)
            
            # Store in context
            context.set(self.output_key, rendered)
            
            # Track what was rendered (for debugging)
            context.add_log(
                node_name=self.name,
                status="success",
                started_at=context.metadata.get("started_at", ""),
                details={
                    "template_length": len(template_str),
                    "output_length": len(rendered),
                },
            )
            
        except TemplateError as e:
            raise ValueError(f"Template rendering error: {e}")
        
        return context
    
    def __repr__(self) -> str:
        return f"PromptNode(name='{self.name}', output_key='{self.output_key}')"


class PromptTemplate:
    """
    Reusable prompt template definition.
    
    Store templates separately from nodes for reusability.
    """
    
    def __init__(
        self,
        name: str,
        template: str,
        description: Optional[str] = None,
        variables: Optional[Dict[str, str]] = None,
    ):
        self.name = name
        self.template = template
        self.description = description
        self.variables = variables or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "template": self.template,
            "description": self.description,
            "variables": self.variables,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PromptTemplate":
        return cls(
            name=data["name"],
            template=data["template"],
            description=data.get("description"),
            variables=data.get("variables"),
        )
    
    def create_node(
        self,
        name: Optional[str] = None,
        output_key: Optional[str] = None,
    ) -> PromptNode:
        """Create a PromptNode from this template"""
        return PromptNode(
            name=name or f"{self.name}_node",
            template=self.template,
            variables=self.variables,
            output_key=output_key or "prompt",
        )


# Built-in prompt templates
BUILTIN_TEMPLATES = {
    "summarize": PromptTemplate(
        name="summarize",
        template="Summarize the following text concisely:\n\n{{ text }}",
        description="Summarize text",
        variables={"text": "user_input"},
    ),
    "analyze": PromptTemplate(
        name="analyze",
        template="Analyze the following {{ content_type }}:\n\n{{ content }}\n\nProvide insights on: {{ focus }}",
        description="Analyze content",
        variables={"content": "user_input", "content_type": "content_type", "focus": "analysis_focus"},
    ),
    "extract": PromptTemplate(
        name="extract",
        template="Extract {{ extract_type }} from the following text:\n\n{{ text }}\n\nFormat the output as {{ format }}.",
        description="Extract information from text",
        variables={"text": "user_input", "extract_type": "extract_type", "format": "output_format"},
    ),
    "classify": PromptTemplate(
        name="classify",
        template="Classify the following text into one of these categories: {{ categories }}\n\nText: {{ text }}\n\nReturn only the category name.",
        description="Classify text into categories",
        variables={"text": "user_input", "categories": "categories"},
    ),
    "translate": PromptTemplate(
        name="translate",
        template="Translate the following text to {{ target_language }}:\n\n{{ text }}",
        description="Translate text",
        variables={"text": "user_input", "target_language": "target_language"},
    ),
}