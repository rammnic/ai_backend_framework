"""
WebSearchNode - Node for web search functionality
"""

from typing import Any, Dict, List, Optional
import os
import json
import urllib.parse

import httpx

from ..core.base_node import BaseNode
from ..core.context import Context


class WebSearchNode(BaseNode):
    """
    Node for performing web searches.
    
    Features:
    - DuckDuckGo search (free, no API key required)
    - SerpAPI support (optional, for better results)
    - Configurable result count
    - Result summarization
    
    Configuration:
        query: Search query string or context key reference (e.g., "$user_input")
        max_results: Maximum number of results (default: 5)
        provider: Search provider - "duckduckgo" or "serpapi" (default: "duckduckgo")
        input_key: Context key for query if not using query param
        output_key: Context key to store results (default: "search_results")
        include_snippets: Include page snippets in results (default: True)
    
    Environment:
        SERPAPI_KEY: API key for SerpAPI (optional)
    """
    
    DUCKDUCKGO_URL = "https://api.duckduckgo.com/"
    SERPAPI_URL = "https://serpapi.com/search.json"
    
    def __init__(
        self,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        *,
        query: Optional[str] = None,
        max_results: int = 5,
        provider: str = "duckduckgo",
        input_key: str = "user_input",
        output_key: str = "search_results",
        include_snippets: bool = True,
    ):
        super().__init__(name, config)
        
        self.query = self.get_config("query", query)
        self.max_results = self.get_config("max_results", max_results)
        self.provider = self.get_config("provider", provider)
        self.input_key = self.get_config("input_key", input_key)
        self.output_key = self.get_config("output_key", output_key)
        self.include_snippets = self.get_config("include_snippets", include_snippets)
    
    def _get_query(self, context: Context) -> str:
        """Get search query from config or context"""
        if self.query:
            if self.query.startswith("$"):
                return context.get(self.query[1:], "")
            return self.query
        return context.get(self.input_key, "")
    
    async def _search_duckduckgo(self, query: str) -> List[Dict[str, Any]]:
        """Search using DuckDuckGo API"""
        results = []
        
        params = {
            "q": query,
            "format": "json",
            "no_html": 1,
            "skip_disambig": 1,
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.DUCKDUCKGO_URL,
                params=params,
                timeout=30.0,
            )
            
            if response.status_code != 200:
                raise Exception(f"DuckDuckGo API error: {response.status_code}")
            
            data = response.json()
            
            # Get related topics
            for topic in data.get("RelatedTopics", [])[:self.max_results]:
                if "Text" in topic and "FirstURL" in topic:
                    results.append({
                        "title": topic.get("Text", "").split(" - ")[0] if " - " in topic.get("Text", "") else topic.get("Text", ""),
                        "url": topic.get("FirstURL", ""),
                        "snippet": topic.get("Text", "") if self.include_snippets else "",
                    })
            
            # If no related topics, try abstract
            if not results and data.get("Abstract"):
                results.append({
                    "title": data.get("Heading", ""),
                    "url": data.get("AbstractURL", ""),
                    "snippet": data.get("Abstract", "") if self.include_snippets else "",
                })
        
        return results
    
    async def _search_serpapi(self, query: str) -> List[Dict[str, Any]]:
        """Search using SerpAPI"""
        api_key = os.getenv("SERPAPI_KEY")
        if not api_key:
            raise ValueError("SERPAPI_KEY not set")
        
        results = []
        
        params = {
            "q": query,
            "api_key": api_key,
            "num": self.max_results,
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.SERPAPI_URL,
                params=params,
                timeout=30.0,
            )
            
            if response.status_code != 200:
                raise Exception(f"SerpAPI error: {response.status_code}")
            
            data = response.json()
            
            for item in data.get("organic_results", [])[:self.max_results]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", "") if self.include_snippets else "",
                })
        
        return results
    
    async def run(self, context: Context) -> Context:
        """Execute web search"""
        query = self._get_query(context)
        
        if not query:
            raise ValueError("No search query provided")
        
        if self.provider == "serpapi":
            results = await self._search_serpapi(query)
        else:
            results = await self._search_duckduckgo(query)
        
        # Store results
        context.set(self.output_key, results)
        context.set(f"{self.output_key}_query", query)
        
        # Log
        context.add_log(
            node_name=self.name,
            status="success",
            started_at=context.metadata.get("started_at", ""),
            details={
                "query": query,
                "provider": self.provider,
                "results_count": len(results),
            },
        )
        
        return context
    
    def __repr__(self) -> str:
        return f"WebSearchNode(name='{self.name}', provider='{self.provider}')"


class WebFetchNode(BaseNode):
    """
    Node for fetching web page content.
    
    Features:
    - Fetch page content by URL
    - Extract text from HTML
    - Configurable content extraction
    
    Configuration:
        url: URL to fetch or context key reference
        input_key: Context key for URL if not using url param
        output_key: Context key to store content (default: "page_content")
        max_length: Maximum content length (default: 10000)
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        *,
        url: Optional[str] = None,
        input_key: str = "url",
        output_key: str = "page_content",
        max_length: int = 10000,
    ):
        super().__init__(name, config)
        
        self.url = self.get_config("url", url)
        self.input_key = self.get_config("input_key", input_key)
        self.output_key = self.get_config("output_key", output_key)
        self.max_length = self.get_config("max_length", max_length)
    
    def _get_url(self, context: Context) -> str:
        """Get URL from config or context"""
        if self.url:
            if self.url.startswith("$"):
                return context.get(self.url[1:], "")
            return self.url
        return context.get(self.input_key, "")
    
    async def run(self, context: Context) -> Context:
        """Fetch web page content"""
        url = self._get_url(context)
        
        if not url:
            raise ValueError("No URL provided")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                timeout=30.0,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; AIFlowEngine/1.0)"
                },
            )
            
            if response.status_code != 200:
                raise Exception(f"Failed to fetch page: {response.status_code}")
            
            content = response.text
            
            # Simple HTML to text extraction
            # Remove script and style tags
            import re
            content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
            # Remove HTML tags
            content = re.sub(r'<[^>]+>', ' ', content)
            # Clean up whitespace
            content = re.sub(r'\s+', ' ', content).strip()
            
            # Truncate if needed
            if len(content) > self.max_length:
                content = content[:self.max_length] + "..."
        
        context.set(self.output_key, content)
        context.set(f"{self.output_key}_url", url)
        
        return context
    
    def __repr__(self) -> str:
        return f"WebFetchNode(name='{self.name}')"