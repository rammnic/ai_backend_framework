"""
ConditionNode - Node for conditional branching in pipelines
"""

from typing import Any, Callable, Dict, Optional, Union

from ..core.base_node import BaseNode
from ..core.context import Context


class ConditionNode(BaseNode):
    """
    Node for conditional branching in pipelines.
    
    Evaluates a condition and sets the next node based on the result.
    Supports multiple condition types:
    - Simple key-value comparison
    - Custom evaluation function
    - Expression evaluation
    
    Configuration:
        condition: Condition to evaluate (see Condition types below)
        on_true: Node name to execute if condition is true
        on_false: Node name to execute if condition is false
        output_key: Context key to store result (optional)
    
    Condition types:
        - dict: {"key": "context_key", "operator": "==", "value": "expected"}
        - callable: Function that takes context and returns bool
        - str: Simple expression like "context.data['key'] == 'value'"
    
    Operators:
        - ==, !=, >, <, >=, <= : Comparison
        - contains : Check if value is in list/string
        - exists : Check if key exists
        - empty : Check if value is empty
    
    Example:
        ConditionNode(
            condition={"key": "sentiment", "operator": "==", "value": "positive"},
            on_true="positive_handler",
            on_false="negative_handler"
        )
    """
    
    OPERATORS = {
        "==": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
        ">": lambda a, b: a > b,
        "<": lambda a, b: a < b,
        ">=": lambda a, b: a >= b,
        "<=": lambda a, b: a <= b,
        "contains": lambda a, b: b in a if a else False,
        "not_contains": lambda a, b: b not in a if a else True,
        "exists": lambda a, b: a is not None,
        "not_exists": lambda a, b: a is None,
        "empty": lambda a, b: not a,
        "not_empty": lambda a, b: bool(a),
        "starts_with": lambda a, b: str(a).startswith(str(b)) if a else False,
        "ends_with": lambda a, b: str(a).endswith(str(b)) if a else False,
    }
    
    def __init__(
        self,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        *,
        condition: Optional[Union[Dict[str, Any], Callable[[Context], bool], str]] = None,
        on_true: Optional[str] = None,
        on_false: Optional[str] = None,
        output_key: Optional[str] = None,
    ):
        super().__init__(name, config)
        
        self.condition = self.get_config("condition", condition)
        self.on_true = self.get_config("on_true", on_true)
        self.on_false = self.get_config("on_false", on_false)
        self.output_key = self.get_config("output_key", output_key)
    
    def _evaluate_dict_condition(self, context: Context) -> bool:
        """Evaluate dictionary-based condition"""
        cond = self.condition
        
        if isinstance(cond, dict):
            key = cond.get("key")
            operator = cond.get("operator", "==")
            expected = cond.get("value")
            
            if not key:
                raise ValueError("Condition dict must have 'key' field")
            
            actual = context.get(key)
            
            if operator not in self.OPERATORS:
                raise ValueError(f"Unknown operator: {operator}")
            
            return self.OPERATORS[operator](actual, expected)
        
        return False
    
    def _evaluate_callable_condition(self, context: Context) -> bool:
        """Evaluate function-based condition"""
        if callable(self.condition):
            return self.condition(context)
        return False
    
    def _evaluate_string_condition(self, context: Context) -> bool:
        """Evaluate string expression condition"""
        if isinstance(self.condition, str):
            # Simple expression evaluation
            # Support: "key == value", "key != value" patterns
            expression = self.condition.strip()
            
            # Create evaluation context
            eval_context = {
                "context": context,
                "data": context.data,
                "get": context.get,
                "true": True,
                "false": False,
                "none": None,
            }
            
            try:
                result = eval(expression, {"__builtins__": {}}, eval_context)
                return bool(result)
            except Exception as e:
                raise ValueError(f"Condition evaluation error: {e}")
        
        return False
    
    def _evaluate(self, context: Context) -> bool:
        """Evaluate the condition"""
        if self.condition is None:
            raise ValueError("No condition provided")
        
        if isinstance(self.condition, dict):
            return self._evaluate_dict_condition(context)
        elif callable(self.condition):
            return self._evaluate_callable_condition(context)
        elif isinstance(self.condition, str):
            return self._evaluate_string_condition(context)
        else:
            raise ValueError(f"Invalid condition type: {type(self.condition)}")
    
    async def run(self, context: Context) -> Context:
        """Evaluate condition and set next node"""
        result = self._evaluate(context)
        
        # Store result if output_key is set
        if self.output_key:
            context.set(self.output_key, result)
        
        # Set next node based on result
        if result:
            if self.on_true:
                self.set_next(self.on_true)
        else:
            if self.on_false:
                self.set_next(self.on_false)
        
        # Log the decision
        context.add_log(
            node_name=self.name,
            status="success",
            started_at=context.metadata.get("started_at", ""),
            details={
                "condition_result": result,
                "next_node": self.next_node,
            },
        )
        
        return context
    
    def __repr__(self) -> str:
        return f"ConditionNode(name='{self.name}', on_true='{self.on_true}', on_false='{self.on_false}')"


class SwitchNode(BaseNode):
    """
    Node for multi-way branching based on a value.
    
    Like a switch/case statement for pipelines.
    
    Configuration:
        key: Context key to get the value from
        cases: Dict mapping values to node names
        default: Default node name if no case matches
    
    Example:
        SwitchNode(
            key="category",
            cases={
                "news": "news_handler",
                "sports": "sports_handler",
                "tech": "tech_handler",
            },
            default="default_handler"
        )
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        *,
        key: str = "",
        cases: Optional[Dict[str, str]] = None,
        default: Optional[str] = None,
    ):
        super().__init__(name, config)
        
        self.key = self.get_config("key", key)
        self.cases = self.get_config("cases", cases) or {}
        self.default = self.get_config("default", default)
    
    async def run(self, context: Context) -> Context:
        """Evaluate value and route to appropriate case"""
        value = context.get(self.key)
        
        # Find matching case
        next_node = self.cases.get(str(value), self.default)
        
        if next_node:
            self.set_next(next_node)
        
        # Log the decision
        context.add_log(
            node_name=self.name,
            status="success",
            started_at=context.metadata.get("started_at", ""),
            details={
                "switch_value": value,
                "matched_case": next_node,
            },
        )
        
        return context
    
    def __repr__(self) -> str:
        return f"SwitchNode(name='{self.name}', key='{self.key}', cases={list(self.cases.keys())})"