"""
ImageAnalysisNode - Node for image analysis via OpenRouter Vision
"""

from typing import Any, Dict, List, Optional, AsyncGenerator
import os
import json
import base64

import httpx

from ..core.base_node import BaseNode
from ..core.context import Context


class ImageAnalysisNode(BaseNode):
    """
    Node for analyzing images using vision models via OpenRouter.
    
    Features:
    - Image analysis via vision-capable models
    - Support for local files and URLs
    - Multiple image analysis in one request
    - Streaming support
    
    Configuration:
        model: Vision model (default: "google/gemini-3-flash-preview")
        prompt: Analysis prompt/instruction
        image_path: Path to image file or context key reference
        image_paths: List of image paths for multi-image analysis
        image_url: URL to image
        input_key: Context key for image path(s)
        output_key: Context key to store analysis result
        max_tokens: Maximum tokens in response
    
    Supported models:
    - google/gemini-3-flash-preview (default)
    - openai/gpt-4o
    - anthropic/claude-3-sonnet
    - Other vision-capable models via OpenRouter
    
    Environment:
        OPENROUTER_API_KEY: API key for OpenRouter
    """
    
    DEFAULT_API_URL = "https://openrouter.ai/api/v1/chat/completions"
    DEFAULT_MODEL = "google/gemini-3-flash-preview"
    
    def __init__(
        self,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        *,
        model: str = DEFAULT_MODEL,
        prompt: Optional[str] = None,
        image_path: Optional[str] = None,
        image_paths: Optional[List[str]] = None,
        image_url: Optional[str] = None,
        input_key: str = "image_path",
        output_key: str = "image_analysis",
        max_tokens: int = 1024,
    ):
        super().__init__(name, config)
        
        self.model = self.get_config("model", model)
        self.prompt = self.get_config("prompt", prompt) or "Analyze this image and describe what you see."
        self.image_path = self.get_config("image_path", image_path)
        self.image_paths = self.get_config("image_paths", image_paths)
        self.image_url = self.get_config("image_url", image_url)
        self.input_key = self.get_config("input_key", input_key)
        self.output_key = self.get_config("output_key", output_key)
        self.max_tokens = self.get_config("max_tokens", max_tokens)
        
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
    
    def _encode_image(self, image_path: str) -> str:
        """Encode local image to base64"""
        with open(image_path, "rb") as f:
            return base64.standard_b64encode(f.read()).decode("utf-8")
    
    def _get_mime_type(self, path: str) -> str:
        """Get MIME type from file extension"""
        ext = path.lower().split(".")[-1]
        mime_types = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "webp": "image/webp",
        }
        return mime_types.get(ext, "image/jpeg")
    
    def _resolve_path(self, path: str) -> str:
        """Resolve path - could be local file or URL"""
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return path
    
    def _get_images(self, context: Context) -> List[Dict[str, Any]]:
        """Get image content parts from config or context"""
        images = []
        
        # Get paths from various sources
        paths = []
        
        if self.image_paths:
            paths = self.image_paths
        elif self.image_path:
            paths = [self.image_path]
        elif self.image_url:
            return [{"type": "image_url", "image_url": {"url": self.image_url}}]
        else:
            # Get from context
            context_path = context.get(self.input_key)
            if context_path:
                if isinstance(context_path, list):
                    paths = context_path
                else:
                    paths = [context_path]
        
        for path in paths:
            path = self._resolve_path(path)
            
            if path.startswith("http://") or path.startswith("https://"):
                # URL-based image
                images.append({
                    "type": "image_url",
                    "image_url": {"url": path}
                })
            else:
                # Local file - encode to base64
                try:
                    encoded = self._encode_image(path)
                    mime_type = self._get_mime_type(path)
                    images.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{encoded}"
                        }
                    })
                except FileNotFoundError:
                    raise ValueError(f"Image file not found: {path}")
        
        return images
    
    def _build_messages(self, context: Context) -> List[Dict[str, Any]]:
        """Build messages with text and images"""
        images = self._get_images(context)
        
        # Build content array
        content = []
        
        # Add text prompt
        content.append({
            "type": "text",
            "text": self.prompt,
        })
        
        # Add images
        content.extend(images)
        
        return [{"role": "user", "content": content}]
    
    async def run(self, context: Context) -> Context:
        """Execute image analysis"""
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not set")
        
        messages = self._build_messages(context)
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
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
            
            # Store metadata
            if "usage" in data:
                context.set("_vision_usage", data["usage"])
        
        return context
    
    async def stream(self, context: Context) -> AsyncGenerator[Context, None]:
        """Execute image analysis with streaming"""
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not set")
        
        messages = self._build_messages(context)
        
        payload = {
            "model": self.model,
            "messages": messages,
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
                                yield context
                        except json.JSONDecodeError:
                            continue
        
        # Final update
        context.set(self.output_key, full_content)
        yield context
    
    def __repr__(self) -> str:
        return f"ImageAnalysisNode(name='{self.name}', model='{self.model}')"


class ImageGenerationNode(BaseNode):
    """
    Node for generating images via OpenRouter/image APIs.
    
    Note: Image generation requires a model that supports it.
    Check OpenRouter for available image generation models.
    
    Configuration:
        prompt: Generation prompt
        model: Image generation model
        output_key: Context key to store result (image URL or data)
        size: Image size (e.g., "1024x1024")
    
    Example:
        ImageGenerationNode(
            prompt="A serene landscape with mountains",
            model="openai/dall-e-3",
            output_key="generated_image"
        )
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        *,
        prompt: Optional[str] = None,
        model: str = "openai/dall-e-3",
        input_key: str = "user_input",
        output_key: str = "generated_image",
        size: str = "1024x1024",
    ):
        super().__init__(name, config)
        
        self.prompt = self.get_config("prompt", prompt)
        self.model = self.get_config("model", model)
        self.input_key = self.get_config("input_key", input_key)
        self.output_key = self.get_config("output_key", output_key)
        self.size = self.get_config("size", size)
        
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.api_url = os.getenv("OPENROUTER_API_URL", "https://openrouter.ai/api/v1/images/generations")
    
    async def run(self, context: Context) -> Context:
        """Generate image"""
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not set")
        
        prompt = self.prompt or context.get(self.input_key, "")
        
        if not prompt:
            raise ValueError("No prompt provided for image generation")
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "n": 1,
            "size": self.size,
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=60.0,
            )
            
            if response.status_code != 200:
                raise Exception(f"Image generation error: {response.status_code} - {response.text}")
            
            data = response.json()
            
            # Get image URL from response
            if "data" in data and len(data["data"]) > 0:
                image_url = data["data"][0].get("url") or data["data"][0].get("b64_json")
                context.set(self.output_key, image_url)
                context.set(f"{self.output_key}_prompt", prompt)
        
        return context
    
    def __repr__(self) -> str:
        return f"ImageGenerationNode(name='{self.name}', model='{self.model}')"