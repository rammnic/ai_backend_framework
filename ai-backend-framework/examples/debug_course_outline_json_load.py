"""Debug script: fetch course_outline_raw and test robust json.loads repair.

Goal:
- Understand why JsonParseNode still returns a string (not list/dict).
- Print json.loads exception details.

Run:
  python ai_backend_framework/ai-backend-framework/examples/debug_course_outline_json_load.py
"""

from __future__ import annotations

import json
import urllib.request
import re
from typing import Any
import ast


def escape_literal_newlines_in_json_strings(s: str) -> str:
    """Escape actual newline characters inside JSON string literals.

    Mirrors JsonParseNode's logic: a quote terminates a JSON string only if
    it is not escaped by an odd number of consecutive backslashes.
    """

    out: list[str] = []
    in_string = False
    backslash_run = 0

    for ch in s:
        if not in_string:
            if ch == '"':
                in_string = True
                backslash_run = 0
            out.append(ch)
            continue

        # inside string
        if ch == '\\':
            backslash_run += 1
            out.append(ch)
            continue

        if ch == '"':
            if backslash_run % 2 == 0:
                in_string = False
            backslash_run = 0
            out.append(ch)
            continue

        backslash_run = 0

        if ch == '\n':
            out.append('\\n')
        elif ch == '\r':
            out.append('\\r')
        elif ch == '\t':
            out.append('\\t')
        elif ch == '\u2028' or ch == '\u2029':
            out.append('\\n')
        else:
            out.append(ch)

    return ''.join(out)


def repair_json_like(s: str) -> str:
    """Best-effort repair matching JsonParseNode._try_load_variants."""

    repaired = escape_literal_newlines_in_json_strings(s)

    # remove double comma artifacts: ...",\n,\n"children": ...
    repaired = re.sub(
        r",\s*,(?=\s*(\"|\{|\[|\]|\}))",
        ",",
        repaired,
    )

    # remove standalone comma-only lines
    repaired = re.sub(r"(?m)^[ \t]*,[ \t]*$", "", repaired)

    # remove standalone closing bracket line directly before object close
    repaired = re.sub(
        r"(?m)^[ \t]*\][ \t]*$\r?\n(?=[ \t]*\})",
        "",
        repaired,
    )

    # remove double closing brackets before object close
    repaired = re.sub(r"\]\s*\]\s*(?=\})", "]", repaired)

    # normalize trailing commas
    repaired = remove_trailing_commas(repaired)

    # unescape escaped quotes
    repaired = repaired.replace(r'\\"', '"').replace(r'\"', '"')

    return repaired


def remove_trailing_commas(s: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", s)


def extract_first_array(text: str) -> str:
    i = text.find("[")
    j = text.rfind("]")
    if i == -1 or j == -1 or j <= i:
        raise ValueError("Could not locate array bounds")
    return text[i : j + 1]


def main() -> None:
    url = "http://localhost:8000/execute"

    pipeline = {
        "name": "course_outline_debug_raw_only",
        "nodes": [
            {
                "type": "PromptNode",
                "name": "prepare_prompt",
                "config": {
                    "template": "You are an expert curriculum designer. Create a detailed course outline based on the following input:\n\nTopic: {{user_prompt}}\nDifficulty: {{difficulty}}\nMax depth: {{depth_limit}}\n\nGenerate a JSON ARRAY (not an object) of topics with the following structure:\n[\n  {\n    \"title\": \"Topic Title\",\n    \"description\": \"Brief description\",\n    \"children\": [\n      {\n        \"title\": \"Subtopic Title\",\n        \"description\": \"Brief description\"\n      }\n    ]\n  }\n]\n\nReturn ONLY the JSON array. Do NOT wrap in code fences.",
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
        ],
    }

    input_data = {
        "user_prompt": "Хочу вкатиться в devops, есть бэкграунд админом сопровождения.",
        "difficulty": "intermediate",
        "depth_limit": 3,
        "user_id": "demo-user-1",
    }

    payload = {
        "pipeline": pipeline,
        "input_data": input_data,
        "stream": False,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

    with urllib.request.urlopen(req, timeout=180) as resp:
        body = resp.read().decode("utf-8")

    out = json.loads(body)
    if not out.get("success"):
        print("LLM pipeline failed:", out.get("data"))
        return

    raw = out["data"].get("course_outline_raw")
    print("raw type:", type(raw).__name__)
    print("raw preview:", str(raw)[:300].replace("\n", "\\n"))

    arr = extract_first_array(raw)
    print("extracted array preview:", arr[:200].replace("\n", "\\n"))

    # Try json.loads without repair
    try:
        parsed1: Any = json.loads(arr)
        print("json.loads(arr) OK; type:", type(parsed1).__name__)
    except Exception as e:
        print("json.loads(arr) FAIL:", type(e).__name__, str(e)[:400])
        if hasattr(e, "pos"):
            pos = getattr(e, "pos")
            print("error pos:", pos)
            snippet = arr[max(0, pos-400):pos+400]
            print("error snippet(800ch window):", snippet.replace("\n", "\\n"))
        if hasattr(e, "lineno") and hasattr(e, "colno"):
            lineno = getattr(e, "lineno")
            colno = getattr(e, "colno")
            lines = arr.splitlines()
            if 1 <= lineno <= len(lines):
                line = lines[lineno-1]
                print(f"error line {lineno}:", line)
                caret = " " * (max(colno-1,0)) + "^"
                print(" " * (len(str(lineno))+10) + caret)  # align roughly under line
                lo = max(0, lineno - 6)
                hi = min(len(lines), lineno + 5)
                print(f"lines[{lo}:{hi}] around error:")
                for idx in range(lo, hi):
                    print(f"{idx+1:04d}: {lines[idx]}")

    print("arr tail (last 25 lines):")
    tail_lines = arr.splitlines()[-25:]
    for i, ln in enumerate(tail_lines, start=max(1, len(arr.splitlines()) - len(tail_lines) + 1)):
        print(f"{i:04d}: {ln}")

    repaired = repair_json_like(arr)
    try:
        parsed2: Any = json.loads(repaired)
        print("json.loads(repaired) OK; type:", type(parsed2).__name__)
        if isinstance(parsed2, list) and parsed2:
            print("first keys:", list(parsed2[0].keys())[:10])
    except Exception as e:
        print("json.loads(repaired) FAIL:", type(e).__name__, str(e)[:400])
        if hasattr(e, "pos"):
            pos = getattr(e, "pos")
            print("error pos:", pos)
            snippet = repaired[max(0, pos-400):pos+400]
            print("repaired error snippet(800ch window):", snippet.replace("\n", "\\n"))
        if hasattr(e, "lineno") and hasattr(e, "colno"):
            lineno = getattr(e, "lineno")
            colno = getattr(e, "colno")
            lines = repaired.splitlines()
            if 1 <= lineno <= len(lines):
                line = lines[lineno-1]
                print(f"error line {lineno}:", line)
                caret = " " * (max(colno-1,0)) + "^"
                print(" " * (len(str(lineno))+10) + caret)
                lo = max(0, lineno - 6)
                hi = min(len(lines), lineno + 5)
                print(f"repaired lines[{lo}:{hi}] around error:")
                for idx in range(lo, hi):
                    print(f"{idx+1:04d}: {lines[idx]}")

        # Last-resort: try Python-literal style parsing.
        try:
            py = repaired
            py = py.replace("null", "None")
            py = py.replace("true", "True")
            py = py.replace("false", "False")
            parsed_py = ast.literal_eval(py)
            print("ast.literal_eval(repaired) OK; type:", type(parsed_py).__name__)
        except Exception as e2:
            print("ast.literal_eval(repaired) FAIL:", type(e2).__name__, str(e2)[:400])

    # Extra: try removing trailing commas BEFORE escaping newlines too.
    arr2 = remove_trailing_commas(arr)
    repaired3 = escape_literal_newlines_in_json_strings(arr2)
    try:
        parsed3: Any = json.loads(repaired3)
        print("json.loads(arr with trailing-comma removed) OK; type:", type(parsed3).__name__)
    except Exception as e:
        print("json.loads(arr2 repaired) FAIL:", type(e).__name__, str(e)[:400])

        if hasattr(e, "pos"):
            pos = getattr(e, "pos")
            print("error pos:", pos)
            snippet = repaired3[max(0, pos-400):pos+400]
            print("repaired3 error snippet(800ch window):", snippet.replace("\n", "\\n"))


if __name__ == "__main__":
    main()
