"""
LLMNode - Node for LLM interactions via OpenRouter
"""

from typing import Any, Dict, List, Optional, AsyncGenerator
import os
import json

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
    
    Configuration:
        model: Model identifier (e.g., "openai/gpt-4", "anthropic/claude-3")
        prompt: System prompt or instruction
        input_key: Context key to read input from (default: "user_input")
        output_key: Context key to write output to (default: "llm_response")
        temperature: Sampling temperature (default: 0.7)
        max_tokens: Maximum tokens to generate (default: 1024)
        streaming: Enable streaming mode (default: False)
        include_history: Include conversation history (default: False)
    
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
    
    async def run(self, context: Context) -> Context:
        """Execute LLM request"""
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not set")
        
        messages = self._build_messages(context)
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        
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
            content = data["choices"][0]["message"]["content"]
            
            # Update context
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
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }
        
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
        
        # Final update
        context.set(self.output_key, full_content)
        context.add_to_history("assistant", full_content, {"model": self.model})
        
        # Remove temporary streaming key
        if "_streaming_chunk" in context.data:
            del context.data["_streaming_chunk"]
        
        yield context
    
    def __repr__(self) -> str:
        return f"LLMNode(name='{self.name}', model='{self.model}')"