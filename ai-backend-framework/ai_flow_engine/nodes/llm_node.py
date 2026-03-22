"""
LLMNode - Node for LLM interactions via OpenRouter
"""

from typing import Any, Dict, List, Optional, AsyncGenerator
import os
import json
from datetime import datetime

import httpx

from ..core.base_node import BaseNode
from ..core.context import Context


class LLMNode(BaseNode):
    """
    Node for interacting with LLM via OpenRouter API.
    
    Features:
    - Text generation via OpenRouter
    - Streaming support
    - Context history integration
    - Customizable models and parameters
    - Structured JSON output (response_format)
    
    Configuration:
        model: Model identifier (e.g., "openai/gpt-4", "anthropic/claude-3")
        prompt: System prompt or instruction
        input_key: Context key to read input from (default: "user_input")
        output_key: Context key to write output to (default: "llm_response")
        temperature: Sampling temperature (default: 0.7)
        max_tokens: Maximum tokens to generate (default: 1024)
        streaming: Enable streaming mode (default: False)
        include_history: Include conversation history (default: False)
        json_mode: Enable structured JSON output (default: False)
        json_schema: JSON Schema for structured output (optional, requires json_mode: true)
        schema_name: Name for the schema (default: "output")
    
    Environment:
        OPENROUTER_API_KEY: API key for OpenRouter
    """
    
    DEFAULT_API_URL = "https://openrouter.ai/api/v1/chat/completions"
    
    def __init__(
        self,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        *,
        model: str = "openai/gpt-4o-mini",
        prompt: Optional[str] = None,
        input_key: str = "user_input",
        output_key: str = "llm_response",
        temperature: float = 0.7,
        max_tokens: int = 1024,
        streaming: bool = False,
        include_history: bool = False,
        json_mode: bool = False,
        json_schema: Optional[Dict[str, Any]] = None,
        schema_name: str = "output",
    ):
        super().__init__(name, config)
        
        # Merge config with explicit parameters
        self.model = self.get_config("model", model)
        self.prompt = self.get_config("prompt", prompt)
        self.input_key = self.get_config("input_key", input_key)
        self.output_key = self.get_config("output_key", output_key)
        self.temperature = self.get_config("temperature", temperature)
        self.max_tokens = self.get_config("max_tokens", max_tokens)
        self.streaming = self.get_config("streaming", streaming)
        self.include_history = self.get_config("include_history", include_history)
        self.json_mode = self.get_config("json_mode", json_mode)
        self.json_schema = self.get_config("json_schema", json_schema)
        self.schema_name = self.get_config("schema_name", schema_name)
        
        # API configuration
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.api_url = os.getenv("OPENROUTER_API_URL", self.DEFAULT_API_URL)
    
    def _get_headers(self) -> Dict[str, str]:
        """Get API headers"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/ai-backend-framework",
            "X-Title": "AI Flow Engine",
        }
    
    def _build_messages(self, context: Context) -> List[Dict[str, str]]:
        """Build messages list for API request"""
        messages = []
        
        # Add system prompt if configured
        if self.prompt:
            # Check if prompt is a template reference
            if self.prompt.startswith("$"):
                template_key = self.prompt[1:]
                prompt_text = context.get(template_key, self.prompt)
            else:
                prompt_text = self.prompt
            messages.append({"role": "system", "content": prompt_text})
        
        # Add conversation history if enabled
        if self.include_history and context.history:
            for msg in context.history:
                messages.append({
                    "role": msg["role"],
                    "content": str(msg["content"]),
                })
        
        # Add user input
        user_input = context.get(self.input_key, "")
        if user_input:
            messages.append({"role": "user", "content": str(user_input)})
        
        return messages
    
    def _build_response_format(self) -> Dict[str, Any]:
        """Build response_format for structured output"""
        if self.json_schema:
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": self.schema_name,
                    "strict": True,
                    "schema": self.json_schema
                }
            }
        elif self.json_mode:
            return {"type": "json_object"}
        return {}
    
    async def run(self, context: Context) -> Context:
        """Execute LLM request"""
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not set")
        
        messages = self._build_messages(context)
        
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        
        # Add structured output for JSON mode
        response_format = self._build_response_format()
        if response_format:
            payload["response_format"] = response_format
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.api_url,
                headers=self._get_headers(),
                json=payload,
                timeout=60.0,
            )
            
            if response.status_code != 200:
                raise Exception(f"OpenRouter API error: {response.status_code} - {response.text}")
            
            data = response.json()
            message = data["choices"][0]["message"]
            
            # For JSON mode, parse the content as JSON
            content = message.get("content", "")
            if self.json_mode and content:
                try:
                    # With response_format: json_object/json_schema, the content is already valid JSON
                    parsed = json.loads(content)
                    context.set(self.output_key, parsed)
                except json.JSONDecodeError as e:
                    # Fallback: store raw content if JSON parsing fails
                    context.set(self.output_key, content)
                    context.add_log(
                        node_name=self.name,
                        status="warning",
                        started_at=datetime.now().isoformat(),
                        details={"message": f"JSON mode: content is not valid JSON, storing as string. Error: {str(e)}"}
                    )
            else:
                context.set(self.output_key, content)
            
            # Add to history
            context.add_to_history("assistant", content, {"model": self.model})
            
            # Store usage info if available
            if "usage" in data:
                context.set("_llm_usage", data["usage"])
        
        return context
    
    async def stream(self, context: Context) -> AsyncGenerator[Context, None]:
        """Execute LLM request with streaming"""
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not set")
        
        messages = self._build_messages(context)
        
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }
        
        # Add structured output for JSON mode (note: streaming with JSON mode may not work with all providers)
        response_format = self._build_response_format()
        if response_format:
            payload["response_format"] = response_format
        
        full_content = ""
        
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                self.api_url,
                headers=self._get_headers(),
                json=payload,
                timeout=60.0,
            ) as response:
                if response.status_code != 200:
                    raise Exception(f"OpenRouter API error: {response.status_code}")
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        
                        try:
                            data = json.loads(data_str)
                            delta = data["choices"][0].get("delta", {})
                            content_chunk = delta.get("content", "")
                            
                            if content_chunk:
                                full_content += content_chunk
                                context.set(self.output_key, full_content)
                                context.set("_streaming_chunk", content_chunk)
                                yield context
                        except json.JSONDecodeError:
                            continue
        
        # For JSON mode, parse the final content as JSON
        if self.json_mode and full_content:
            try:
                parsed = json.loads(full_content)
                context.set(self.output_key, parsed)
            except json.JSONDecodeError:
                context.set(self.output_key, full_content)
        else:
            context.set(self.output_key, full_content)
        
        context.add_to_history("assistant", full_content, {"model": self.model})
        
        # Remove temporary streaming key
        if "_streaming_chunk" in context.data:
            del context.data["_streaming_chunk"]
        
        yield context
    
    def __repr__(self) -> str:
        return f"LLMNode(name='{self.name}', model='{self.model}', json_mode={self.json_mode})"
