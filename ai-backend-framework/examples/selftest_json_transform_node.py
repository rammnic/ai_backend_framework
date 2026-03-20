"""Selftest for JsonTransformNode coercion.

Runs without OpenRouter / network.

Checks that the node can transform:
  - dict with topics array (new format from json_mode)
  - list input (legacy)
  - dict wrapper input (legacy)
  - dict single-topic input
  - string JSON array / JSON array in markdown code block
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any


def _add_repo_to_path() -> None:
    here = os.path.abspath(os.path.dirname(__file__))
    framework_root = os.path.dirname(here)  # ai-backend-framework/
    sys.path.insert(0, framework_root)


_add_repo_to_path()

from ai_flow_engine import Context  # noqa: E402
from ai_flow_engine.nodes import JsonTransformNode  # noqa: E402


async def _run_case(case_name: str, input_value: Any) -> None:
    node = JsonTransformNode(
        name="transform_structure",
        config={
            "input_key": "course_outline",
            "output_key": "structure",
            "default_type": "topic",
        },
    )

    ctx = Context(data={"course_outline": input_value})
    ctx = await node.execute(ctx)

    structure = ctx.get("structure")
    assert isinstance(structure, list), f"{case_name}: structure must be list"
    assert len(structure) >= 1, f"{case_name}: structure must be non-empty"

    first = structure[0]
    assert isinstance(first, dict), f"{case_name}: first topic must be dict"
    assert isinstance(first.get("id"), str) and first["id"], f"{case_name}: missing id"
    assert isinstance(first.get("title"), str) and first["title"], f"{case_name}: missing title"
    print(f"  [OK] {case_name}")


async def main() -> None:
    print("Running JsonTransformNode selftest...")
    print()
    
    topic = {
        "title": "Основы Python",
        "description": "Intro",
        "children": [{"title": "Введение в Python", "description": "What is Python?"}],
    }

    # New format (from json_mode LLM)
    dict_with_topics = {"topics": [topic]}
    
    # Legacy formats
    list_input = [topic]
    dict_wrapper = {"structure": list_input}
    dict_single = topic

    string_json_array = json.dumps(list_input, ensure_ascii=False)
    string_codeblock = f"```json\n{string_json_array}\n```"
    string_json_array_wrapped = json.dumps({"structure": list_input}, ensure_ascii=False)
    string_topics = json.dumps(dict_with_topics, ensure_ascii=False)

    print("Testing NEW format (json_mode):")
    await _run_case("dict_with_topics", dict_with_topics)
    await _run_case("string_topics", string_topics)
    
    print()
    print("Testing LEGACY formats:")
    await _run_case("list_input", list_input)
    await _run_case("dict_wrapper", dict_wrapper)
    await _run_case("dict_single", dict_single)
    await _run_case("string_json_array", string_json_array)
    await _run_case("string_codeblock", string_codeblock)
    await _run_case("string_json_array_wrapped", string_json_array_wrapped)

    print()
    print("=" * 50)
    print("OK: JsonTransformNode selftest passed!")
    print("All formats (including json_mode) work correctly.")


if __name__ == "__main__":
    asyncio.run(main())
