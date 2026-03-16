"""
FastAPI application - REST API for AI Flow Engine
"""

from typing import Any, Dict, List, Optional
import os
import json
import asyncio

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_flow_engine import Context, PipelineRunner, Debugger
from ai_flow_engine.core.engine import Pipeline
from ai_flow_engine.config import PipelineLoader, load_pipeline
from ai_flow_engine.config.loader import EXAMPLE_PIPELINES


# Pydantic models for API
class ExecuteRequest(BaseModel):
    """Request model for pipeline execution"""
    pipeline: Optional[Dict[str, Any]] = Field(None, description="Pipeline configuration (inline)")
    pipeline_name: Optional[str] = Field(None, description="Name of pre-defined pipeline")
    input_data: Dict[str, Any] = Field(default_factory=dict, description="Input data for the pipeline")
    config: Optional[Dict[str, Any]] = Field(None, description="Pipeline configuration overrides")
    stream: bool = Field(False, description="Enable streaming response")


class ExecuteResponse(BaseModel):
    """Response model for pipeline execution"""
    success: bool
    data: Dict[str, Any]
    logs: List[Dict[str, Any]]
    metadata: Dict[str, Any]


class PipelineInfo(BaseModel):
    """Pipeline information model"""
    name: str
    description: Optional[str] = None
    nodes_count: int


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    version: str


# Create FastAPI app
def create_app(
    title: str = "AI Flow Engine API",
    version: str = "0.1.0",
    pipelines_dir: Optional[str] = None,
) -> FastAPI:
    """
    Create FastAPI application.
    
    Args:
        title: API title
        version: API version
        pipelines_dir: Directory containing pipeline configurations
        
    Returns:
        FastAPI application instance
    """
    app = FastAPI(
        title=title,
        version=version,
        description="REST API for AI Flow Engine - Backend framework for AI pipelines",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Initialize components
    loader = PipelineLoader()
    runner = PipelineRunner()
    
    # Load pipelines from directory if specified
    pipelines: Dict[str, Pipeline] = {}
    
    if pipelines_dir and os.path.isdir(pipelines_dir):
        pipelines = loader.load_from_directory(pipelines_dir)
    
    # Add example pipelines
    for name, config in EXAMPLE_PIPELINES.items():
        if name not in pipelines:
            try:
                pipelines[name] = load_pipeline(config)
            except Exception:
                pass
    
    # Store in app state
    app.state.loader = loader
    app.state.runner = runner
    app.state.pipelines = pipelines
    
    # Routes
    @app.get("/", response_model=HealthResponse)
    async def root():
        """Health check endpoint"""
        return HealthResponse(status="ok", version=version)
    
    @app.get("/health", response_model=HealthResponse)
    async def health():
        """Health check endpoint"""
        return HealthResponse(status="ok", version=version)
    
    @app.get("/pipelines", response_model=List[PipelineInfo])
    async def list_pipelines():
        """List available pipelines"""
        result = []
        for name, pipeline in app.state.pipelines.items():
            result.append(PipelineInfo(
                name=name,
                description=pipeline.metadata.get("description"),
                nodes_count=len(pipeline.nodes),
            ))
        return result
    
    @app.get("/pipelines/{name}")
    async def get_pipeline(name: str):
        """Get pipeline configuration"""
        if name not in app.state.pipelines:
            raise HTTPException(status_code=404, detail=f"Pipeline '{name}' not found")
        
        pipeline = app.state.pipelines[name]
        return pipeline.to_dict()
    
    @app.post("/execute", response_model=ExecuteResponse)
    async def execute_pipeline(request: ExecuteRequest):
        """Execute a pipeline"""
        # Get pipeline
        if request.pipeline:
            pipeline = load_pipeline(request.pipeline)
        elif request.pipeline_name:
            if request.pipeline_name not in app.state.pipelines:
                raise HTTPException(
                    status_code=404,
                    detail=f"Pipeline '{request.pipeline_name}' not found"
                )
            pipeline = app.state.pipelines[request.pipeline_name]
        else:
            raise HTTPException(
                status_code=400,
                detail="Either 'pipeline' or 'pipeline_name' must be provided"
            )
        
        # Create context
        context = Context(data=request.input_data)
        
        try:
            # Execute pipeline
            result = await app.state.runner.execute(pipeline, context)
            
            return ExecuteResponse(
                success=True,
                data=result.data,
                logs=result.logs,
                metadata=result.metadata,
            )
        except Exception as e:
            return ExecuteResponse(
                success=False,
                data={"error": str(e)},
                logs=context.logs,
                metadata=context.metadata,
            )
    
    @app.post("/execute/stream")
    async def execute_pipeline_stream(request: ExecuteRequest):
        """Execute a pipeline with streaming response"""
        # Get pipeline
        if request.pipeline:
            pipeline = load_pipeline(request.pipeline)
        elif request.pipeline_name:
            if request.pipeline_name not in app.state.pipelines:
                raise HTTPException(
                    status_code=404,
                    detail=f"Pipeline '{request.pipeline_name}' not found"
                )
            pipeline = app.state.pipelines[request.pipeline_name]
        else:
            raise HTTPException(
                status_code=400,
                detail="Either 'pipeline' or 'pipeline_name' must be provided"
            )
        
        async def generate():
            """Generate streaming response"""
            context = Context(data=request.input_data)
            
            try:
                async for updated_context in app.state.runner.stream(pipeline, context):
                    # Yield JSON chunks
                    chunk = {
                        "data": updated_context.data,
                        "metadata": updated_context.metadata,
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                
                # Final response
                final = {
                    "success": True,
                    "data": context.data,
                    "logs": context.logs,
                    "metadata": context.metadata,
                }
                yield f"data: {json.dumps(final)}\n\n"
            except Exception as e:
                error = {
                    "success": False,
                    "error": str(e),
                    "logs": context.logs,
                }
                yield f"data: {json.dumps(error)}\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
    
    @app.post("/chat")
    async def chat(request: Dict[str, Any]):
        """
        Simple chat endpoint for quick LLM interactions.
        
        Request body:
        {
            "message": "Your message here",
            "model": "openai/gpt-4o-mini" (optional),
            "history": [...] (optional)
        }
        """
        from ai_flow_engine.nodes import LLMNode
        
        message = request.get("message", "")
        model = request.get("model", "openai/gpt-4o-mini")
        history = request.get("history", [])
        
        if not message:
            raise HTTPException(status_code=400, detail="Message is required")
        
        # Create simple chat pipeline
        llm_node = LLMNode(
            name="chat",
            model=model,
            include_history=True,
        )
        
        context = Context(
            data={"user_input": message},
            history=history,
        )
        
        try:
            result = await llm_node.execute(context)
            
            return {
                "success": True,
                "response": result.get("llm_response"),
                "history": result.history,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/chat/stream")
    async def chat_stream(request: Dict[str, Any]):
        """
        Streaming chat endpoint.
        
        Request body:
        {
            "message": "Your message here",
            "model": "openai/gpt-4o-mini" (optional),
            "history": [...] (optional)
        }
        """
        from ai_flow_engine.nodes import LLMNode
        
        message = request.get("message", "")
        model = request.get("model", "openai/gpt-4o-mini")
        history = request.get("history", [])
        
        if not message:
            raise HTTPException(status_code=400, detail="Message is required")
        
        llm_node = LLMNode(
            name="chat_stream",
            model=model,
            streaming=True,
            include_history=True,
        )
        
        context = Context(
            data={"user_input": message},
            history=history,
        )
        
        async def generate():
            """Generate streaming response"""
            full_response = ""
            
            async for updated_context in llm_node.stream(context):
                chunk = updated_context.get("_streaming_chunk", "")
                if chunk:
                    full_response += chunk
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            
            # Final response
            yield f"data: {json.dumps({'done': True, 'response': full_response})}\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
        )
    
    @app.post("/analyze-image")
    async def analyze_image(request: Dict[str, Any]):
        """
        Analyze an image.
        
        Request body:
        {
            "image_path": "path/to/image.jpg" or "image_url": "https://...",
            "prompt": "What's in this image?" (optional),
            "model": "google/gemini-3-flash-preview" (optional)
        }
        """
        from ai_flow_engine.nodes import ImageAnalysisNode
        
        image_path = request.get("image_path")
        image_url = request.get("image_url")
        prompt = request.get("prompt", "Analyze this image and describe what you see.")
        model = request.get("model", "google/gemini-3-flash-preview")
        
        if not image_path and not image_url:
            raise HTTPException(
                status_code=400,
                detail="Either 'image_path' or 'image_url' is required"
            )
        
        image_node = ImageAnalysisNode(
            name="analyze_image",
            model=model,
            prompt=prompt,
            image_path=image_path,
            image_url=image_url,
        )
        
        context = Context()
        
        try:
            result = await image_node.execute(context)
            
            return {
                "success": True,
                "analysis": result.get("image_analysis"),
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/search")
    async def web_search(request: Dict[str, Any]):
        """
        Perform web search.
        
        Request body:
        {
            "query": "search query",
            "max_results": 5 (optional),
            "provider": "duckduckgo" (optional)
        }
        """
        from ai_flow_engine.nodes import WebSearchNode
        
        query = request.get("query", "")
        max_results = request.get("max_results", 5)
        provider = request.get("provider", "duckduckgo")
        
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")
        
        search_node = WebSearchNode(
            name="search",
            query=query,
            max_results=max_results,
            provider=provider,
        )
        
        context = Context()
        
        try:
            result = await search_node.execute(context)
            
            return {
                "success": True,
                "results": result.get("search_results"),
                "query": result.get("search_results_query"),
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    return app


# Default app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)