"""Selftest for JsonTransformNode coercion.

Runs without OpenRouter / network.

Checks that the node can transform:
  - list input
  - dict wrapper input
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


async def main() -> None:
    topic = {
        "title": "Основы Python",
        "description": "Intro",
        "children": [{"title": "Введение в Python", "description": "What is Python?"}],
    }

    list_input = [topic]
    dict_wrapper = {"structure": list_input}
    dict_single = topic

    string_json_array = json.dumps(list_input, ensure_ascii=False)
    string_codeblock = f"```json\n{string_json_array}\n```"
    string_json_array_wrapped = json.dumps({"structure": list_input}, ensure_ascii=False)

    # Tricky case: JSON-ish content where newlines are represented as literal "\\n"
    # and quotes are escaped as \" (this mirrors what we often see from LLM toolchains
    # after JSON extraction failures).
    pretty = json.dumps(list_input, ensure_ascii=False, indent=2)
    escaped_pretty = pretty.replace("\n", "\\n").replace('"', '\\"')
    escaped_with_fence = f"```json\\n{escaped_pretty}\\n```"

    await _run_case("list_input", list_input)
    await _run_case("dict_wrapper", dict_wrapper)
    await _run_case("dict_single", dict_single)
    await _run_case("string_json_array", string_json_array)
    await _run_case("string_codeblock", string_codeblock)
    await _run_case("string_json_array_wrapped", string_json_array_wrapped)
    await _run_case("string_codeblock_escaped_newlines_quotes", escaped_with_fence)

    print("OK: JsonTransformNode coercion selftest passed")


if __name__ == "__main__":
    asyncio.run(main())
