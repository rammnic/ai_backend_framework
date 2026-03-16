"""
Debugger - Logging and debugging utilities for pipelines
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
import json

from .context import Context


class Debugger:
    """
    Debugger utility for inspecting and logging pipeline execution.
    
    Features:
    - Pretty print context state
    - Export logs to file
    - Analyze execution times
    - Find failed nodes
    """
    
    def __init__(self, context: Optional[Context] = None):
        self.context = context
    
    def set_context(self, context: Context) -> None:
        """Set the context to debug"""
        self.context = context
    
    def print_summary(self) -> str:
        """Print a summary of the pipeline execution"""
        if self.context is None:
            return "No context set"
        
        lines = [
            "=" * 60,
            f"PIPELINE EXECUTION SUMMARY",
            "=" * 60,
            f"Pipeline: {self.context.metadata.get('pipeline_name', 'unknown')}",
            f"Status: {self.context.metadata.get('status', 'unknown')}",
            f"Steps: {self.context.metadata.get('steps_executed', 0)}",
            f"Started: {self.context.metadata.get('started_at', 'unknown')}",
            f"Finished: {self.context.metadata.get('finished_at', 'unknown')}",
            "",
            "DATA KEYS:",
            f"  {list(self.context.data.keys())}",
            "",
            "EXECUTION LOG:",
        ]
        
        for log in self.context.logs:
            status_icon = "✓" if log["status"] == "success" else "✗"
            duration = self._calculate_duration(log["started_at"], log["finished_at"])
            lines.append(f"  {status_icon} {log['node_name']}: {log['status']} ({duration})")
            if log.get("error"):
                lines.append(f"    ERROR: {log['error']}")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    def print_context(self, indent: int = 2) -> str:
        """Pretty print the full context"""
        if self.context is None:
            return "No context set"
        
        return json.dumps(
            self.context.to_dict(),
            indent=indent,
            ensure_ascii=False,
            default=str,
        )
    
    def get_failed_nodes(self) -> List[Dict[str, Any]]:
        """Get list of failed node executions"""
        if self.context is None:
            return []
        
        return [
            log for log in self.context.logs
            if log["status"] == "error"
        ]
    
    def get_successful_nodes(self) -> List[Dict[str, Any]]:
        """Get list of successful node executions"""
        if self.context is None:
            return []
        
        return [
            log for log in self.context.logs
            if log["status"] == "success"
        ]
    
    def get_execution_times(self) -> Dict[str, float]:
        """Get execution times for each node in seconds"""
        if self.context is None:
            return {}
        
        times = {}
        for log in self.context.logs:
            duration = self._calculate_duration(log["started_at"], log["finished_at"])
            if duration:
                times[log["node_name"]] = duration
        
        return times
    
    def get_total_duration(self) -> Optional[float]:
        """Get total pipeline execution time in seconds"""
        if self.context is None:
            return None
        
        started = self.context.metadata.get("started_at")
        finished = self.context.metadata.get("finished_at")
        
        if started and finished:
            return self._calculate_duration(started, finished)
        
        return None
    
    def export_logs(self, filepath: str) -> None:
        """Export logs to a JSON file"""
        if self.context is None:
            raise ValueError("No context set")
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(
                self.context.to_dict(),
                f,
                indent=2,
                ensure_ascii=False,
                default=str,
            )
    
    def find_slow_nodes(self, threshold: float = 1.0) -> List[Dict[str, Any]]:
        """Find nodes that took longer than threshold (in seconds)"""
        times = self.get_execution_times()
        slow = []
        
        if self.context is None:
            return slow
        
        for log in self.context.logs:
            node_name = log["node_name"]
            duration = times.get(node_name, 0)
            
            if duration > threshold:
                slow.append({
                    "node_name": node_name,
                    "duration": duration,
                    "threshold": threshold,
                })
        
        return slow
    
    def _calculate_duration(self, started_at: str, finished_at: str) -> Optional[float]:
        """Calculate duration between two ISO timestamps"""
        try:
            start = datetime.fromisoformat(started_at)
            end = datetime.fromisoformat(finished_at)
            return (end - start).total_seconds()
        except (ValueError, TypeError):
            return None
    
    def __repr__(self) -> str:
        if self.context is None:
            return "Debugger(no context)"
        return f"Debugger(pipeline={self.context.metadata.get('pipeline_name', 'unknown')})"


def print_debug(context: Context) -> str:
    """Quick debug print for context"""
    debugger = Debugger(context)
    return debugger.print_summary()


def export_debug(context: Context, filepath: str) -> None:
    """Quick export for context"""
    debugger = Debugger(context)
    debugger.export_logs(filepath)