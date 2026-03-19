"""Debug helper for course_outline pipeline parsing.

Calls AI framework /execute with a trimmed pipeline:
  prepare_prompt -> generate_outline -> parse_json

Prints types + small previews of:
  - course_outline_raw
  - course_outline (output of JsonParseNode)

Run (from repo root):
  python ai_backend_framework/ai-backend-framework/examples/debug_course_outline_parse.py
"""

from __future__ import annotations

import json
import urllib.request

import os
import sys

# Ensure ai_flow_engine is importable when running from repo root.
HERE = os.path.abspath(os.path.dirname(__file__))
FRAMEWORK_ROOT = os.path.dirname(HERE)  # ai-backend-framework/
sys.path.insert(0, FRAMEWORK_ROOT)

from ai_flow_engine.nodes import JsonParseNode, JsonTransformNode
from ai_flow_engine import Context


def escape_literal_newlines_in_json_strings(s: str) -> str:
    """Escape actual newline characters inside JSON string literals."""

    out: list[str] = []
    in_string = False
    escape = False

    for ch in s:
        if not in_string:
            if ch == '"':
                in_string = True
            out.append(ch)
            continue

        if escape:
            out.append(ch)
            escape = False
            continue

        if ch == '\\':
            out.append(ch)
            escape = True
            continue

        if ch == '"':
            in_string = False
            out.append(ch)
            continue

        if ch == '\n':
            out.append('\\n')
        elif ch == '\r':
            out.append('\\r')
        elif ch == '\t':
            out.append('\\t')
        else:
            out.append(ch)

    return ''.join(out)


async def main() -> None:
    url = "http://localhost:8000/execute"

    pipeline = {
        "name": "course_outline_debug_parse",
        "nodes": [
            {
                "type": "PromptNode",
                "name": "prepare_prompt",
                "config": {
                    "template": "You are an expert curriculum designer. Create a detailed course outline based on the following input:\n\nTopic: {{user_prompt}}\nDifficulty: {{difficulty}}\nMax depth: {{depth_limit}}\n\nGenerate a JSON ARRAY (not an object) of topics with the following structure:\n[\n  {\n    \"title\": \"Topic Title\",\n    \"description\": \"Brief description\",\n    \"children\": [\n      {\n        \"title\": \"Subtopic Title\",\n        \"description\": \"Brief description\"\n      }\n    ]\n  }\n]\n\nSTRICT OUTPUT REQUIREMENTS:\n- Return ONLY the JSON array. No wrapper objects like {\"structure\": ...}.\n- Do NOT include explanations, markdown text, or extra keys outside the array.\n- Wrap the JSON array in a markdown code block: ```json ... ```.\n- Ensure every topic has title/description and children is an array (may be empty).",
                    "output_key": "outline_prompt",
                },
            },
            {
                "type": "LLMNode",
                "name": "generate_outline",
                "config": {
                    "model": "openai/gpt-5.4-nano",
                    "input_key": "outline_prompt",
                    "output_key": "course_outline_raw",
                },
            },
            {
                "type": "JsonParseNode",
                "name": "parse_json",
                "config": {
                    "input_key": "course_outline_raw",
                    "output_key": "course_outline",
                },
            },
        ],
    }

    input_data = {
        "user_prompt": "Хочу вкатиться в devops, есть бэкграунд админом сопровождения.",
        "difficulty": "intermediate",
        "depth_limit": 3,
        "user_id": "demo-user-1",
    }

    req_body = {"pipeline": pipeline, "input_data": input_data, "stream": False}
    data = json.dumps(req_body, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        body = resp.read().decode("utf-8")

    payload = json.loads(body)
    print("success:", payload.get("success"))

    if payload.get("success"):
        d = payload.get("data", {})
        raw = d.get("course_outline_raw")
        parsed = d.get("course_outline")

        # Extra debugging: inspect string form
        if isinstance(raw, str):
            print("raw contains newline?", "\n" in raw)
            print("raw contains literal \\\\n?", "\\n" in raw)

        # Extra debugging: try parsing raw directly with JsonParseNode internals
        parser = JsonParseNode(
            name="parse_json_direct",
            config={"input_key": "course_outline_raw", "output_key": "course_outline"},
        )
        extracted = parser._extract_json_from_markdown(raw) if isinstance(raw, str) else None
        print("extracted type:", type(extracted).__name__)
        if isinstance(extracted, str):
            print("extracted preview:", extracted[:200].replace("\n", "\\n"))

        reparsed = parser._parse_json(raw) if isinstance(raw, str) else None
        print("reparsed type:", type(reparsed).__name__)
        if isinstance(reparsed, (list, dict)):
            if isinstance(reparsed, list):
                print("reparsed list len:", len(reparsed))
            else:
                print("reparsed dict keys:", list(reparsed.keys())[:5])
        else:
            print("reparsed preview:", (reparsed or "")[:200].replace("\n", "\\n"))
        print("course_outline_raw type:", type(raw).__name__)
        if isinstance(raw, str):
            print("course_outline_raw preview:", raw[:300].replace("\n", "\\n"))

        print("course_outline type:", type(parsed).__name__)
        if isinstance(parsed, str):
            print("course_outline preview:", parsed[:300].replace("\n", "\\n"))
        else:
            # list/dict
            print("course_outline keys/len:", (list(parsed)[:1] if isinstance(parsed, list) else list(parsed.keys())[:5]))

        # Try to run JsonTransformNode locally on the parsed output
        try:
            node = JsonTransformNode(
                name="transform_structure_debug",
                config={"input_key": "course_outline", "output_key": "structure"},
            )
            ctx = Context(data={"course_outline": parsed})
            ctx = await node.execute(ctx)  # type: ignore[misc]
            structure = ctx.get("structure")
            print("local transform_structure result type:", type(structure).__name__)
            if isinstance(structure, list):
                print("local structure len:", len(structure))
        except Exception as e:
            print("local JsonTransformNode failed:", str(e)[:500])
    else:
        print("error:", payload.get("data"))


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
