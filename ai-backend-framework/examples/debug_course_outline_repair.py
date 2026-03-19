"""Debug script: try to repair/parse course_outline_raw JSON-like strings.

1) Fetches from LMS backend: POST /api/v1/ai/generate/structure
2) Takes course_outline_raw
3) Extracts first [...] substring
4) Applies repair: escape literal newlines/tabs/carriage returns inside JSON string literals
5) Attempts json.loads and prints diagnostics.

Run:
  python ai_backend_framework/ai-backend-framework/examples/debug_course_outline_repair.py
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any


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

        # inside string
        if escape:
            out.append(ch)
            escape = False
            continue

        if ch == "\\":
            out.append(ch)
            escape = True
            continue

        if ch == '"':
            in_string = False
            out.append(ch)
            continue

        if ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        else:
            out.append(ch)

    return "".join(out)


def extract_first_json_array(text: str) -> str:
    i = text.find("[")
    j = text.rfind("]")
    if i == -1 or j == -1 or j <= i:
        raise ValueError("Could not find JSON array bounds")
    return text[i : j + 1]


def main() -> None:
    url = "http://localhost:8001/api/v1/ai/generate/structure"
    payload = {
        "user_prompt": "Хочу вкатиться в devops, есть бэкграунд админом сопровождения",
        "difficulty": "intermediate",
        "depth_limit": 3,
        "user_id": "demo-user-1",
    }

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        body = resp.read().decode("utf-8")

    top = json.loads(body)
    print("backend success:", top.get("success"))
    print("backend error:", top.get("data", {}).get("error"))

    raw = top.get("data", {}).get("course_outline_raw")
    if not raw:
        # When parsing fails in current pipeline, response may not include raw.
        # In that case, use the error preview isn't enough; abort.
        print("No course_outline_raw in response; cannot debug further")
        return

    arr = extract_first_json_array(raw)
    print("raw arr preview:", arr[:300].replace("\n", "\\n"))

    repaired = escape_literal_newlines_in_json_strings(arr)
    repaired = repaired.replace(",\n\"", ",\n\"")

    try:
        parsed: Any = json.loads(repaired)
        print("json.loads OK; type:", type(parsed).__name__)
        if isinstance(parsed, list) and parsed:
            print("first item keys:", list(parsed[0].keys())[:10])
    except Exception as e:
        print("json.loads FAIL:", type(e).__name__, str(e)[:500])
        # Print a small window around the failing location if possible
        msg = str(e)
        # Some json errors include 'line X column Y'
        print("error msg:", msg)
        # Save repaired snippet for manual inspection
        with open("/tmp/repaired_course_outline_debug.json", "w", encoding="utf-8") as f:
            f.write(repaired)
        print("wrote /tmp/repaired_course_outline_debug.json")


if __name__ == "__main__":
    main()
