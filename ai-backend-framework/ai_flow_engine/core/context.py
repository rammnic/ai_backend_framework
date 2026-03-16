"""
Context - Data bus for communication between nodes
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
import copy


class Context:
    """
    Context is the data bus that flows through all nodes in a pipeline.
    Each node reads from and writes to the same Context object.
    
    Attributes:
        data: Main data dictionary containing all pipeline data
        history: List of messages/interactions for memory
        logs: Debug logs from each node execution
        config: Configuration settings for the pipeline
        metadata: Additional metadata (pipeline_id, timestamps, etc.)
    """
    
    def __init__(
        self,
        data: Optional[Dict[str, Any]] = None,
        history: Optional[List[Dict[str, Any]]] = None,
        config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.data = data or {}
        self.history = history or []
        self.logs: List[Dict[str, Any]] = []
        self.config = config or {}
        self.metadata = metadata or {
            "created_at": datetime.now().isoformat(),
            "pipeline_id": None,
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get value from data by key"""
        return self.data.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set value in data"""
        self.data[key] = value
    
    def update(self, data: Dict[str, Any]) -> None:
        """Update data with new dictionary"""
        self.data.update(data)
    
    def add_to_history(self, role: str, content: Any, metadata: Optional[Dict] = None) -> None:
        """Add message to history"""
        self.history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        })
    
    def add_log(
        self,
        node_name: str,
        status: str,
        started_at: str,
        finished_at: Optional[str] = None,
        error: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add execution log from a node"""
        self.logs.append({
            "node_name": node_name,
            "status": status,
            "started_at": started_at,
            "finished_at": finished_at or datetime.now().isoformat(),
            "error": error,
            "details": details or {},
        })
    
    def get_last_log(self) -> Optional[Dict[str, Any]]:
        """Get the last log entry"""
        return self.logs[-1] if self.logs else None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary"""
        return {
            "data": self.data,
            "history": self.history,
            "logs": self.logs,
            "config": self.config,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Context":
        """Create context from dictionary"""
        context = cls(
            data=data.get("data"),
            history=data.get("history"),
            config=data.get("config"),
            metadata=data.get("metadata"),
        )
        context.logs = data.get("logs", [])
        return context
    
    def copy(self) -> "Context":
        """Create a deep copy of the context"""
        return Context.from_dict(copy.deepcopy(self.to_dict()))
    
    def __repr__(self) -> str:
        return f"Context(data_keys={list(self.data.keys())}, history_len={len(self.history)}, logs_len={len(self.logs)})"