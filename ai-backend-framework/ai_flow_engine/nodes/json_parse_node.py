"""
JsonParseNode - Node for parsing JSON from text/markdown blocks
"""

import json
import re
from typing import Any, Dict, Optional
from datetime import datetime

from ..core.base_node import BaseNode
from ..core.context import Context


class JsonParseNode(BaseNode):
    """
    Node that parses JSON from text that may contain markdown code blocks.
    
    Configuration:
        input_key: Key in context containing the text to parse (required)
        output_key: Key to store parsed JSON in context (default: "parsed_json")
        default_on_error: Default value to use if parsing fails (optional)
    
    Example:
        Input: "```json\n[{\"title\": \"Topic 1\"}]\n```"
        Output: [{"title": "Topic 1"}]
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(name or "JsonParseNode", config)
    
    def _extract_json_from_markdown(self, text: str) -> str:
        """
        Extract JSON from markdown code blocks or plain text.
        
        Handles:
        - ```json ... ``` blocks
        - ``` ... ``` blocks
        - Plain JSON strings
        """
        if not text:
            return text
        
        def _looks_like_json_payload(s: str) -> bool:
            t = s.lstrip()
            return t.startswith("[") or t.startswith("{")

        # Try to find JSON inside fenced code blocks.
        # Be permissive about whitespace around fences.
        json_block_pattern = r"```(?:json)?\s*(.*?)\s*```"
        matches = re.findall(json_block_pattern, text, re.DOTALL | re.IGNORECASE)
        if matches:
            candidate = matches[0].strip()
            if _looks_like_json_payload(candidate):
                return candidate

        # Second pass: normalize escaped newlines to real ones.
        normalized = text.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")
        matches = re.findall(json_block_pattern, normalized, re.DOTALL | re.IGNORECASE)
        if matches:
            candidate = matches[0].strip()
            if _looks_like_json_payload(candidate):
                return candidate

        # Third pass: try full unicode_escape decoding (handles double-escaped sequences).
        try:
            decoded = bytes(text, "utf-8").decode("unicode_escape")
            matches = re.findall(json_block_pattern, decoded, re.DOTALL | re.IGNORECASE)
            if matches:
                candidate = matches[0].strip()
                if _looks_like_json_payload(candidate):
                    return candidate
        except Exception:
            pass

        # Fallback: if fences exist, take inner content between the first and last ```.
        if "```" in text:
            start = text.find("```")
            end = text.rfind("```")
            if start != -1 and end != -1 and end > start:
                inner = text[start + 3 : end]
                # Strip leading language hint like: json
                inner = inner.lstrip()
                if inner.lower().startswith("json"):
                    inner = inner[4:].lstrip()
                return inner.strip()

        # Extra fallback: extract the first JSON array/object substring by brackets.
        # This is more robust than relying on exact markdown code-fence formatting.
        def _extract_balanced_json_substring(s: str) -> str | None:
            """Extract the first balanced JSON array/object substring from text.

            Uses a small stack-based scanner and tracks whether we're inside a JSON string.
            This avoids relying on the *last* `]` / `}` which can be wrong when LLM adds
            extra bracketed text after the JSON payload.
            """

            open_idx_arr = s.find("[")
            open_idx_obj = s.find("{")
            open_idx_candidates = [i for i in (open_idx_arr, open_idx_obj) if i != -1]
            if not open_idx_candidates:
                return None

            start = min(open_idx_candidates)
            start_ch = s[start]
            matching = {"[": "]", "{": "}"}
            expected_close = matching[start_ch]

            stack: list[str] = [expected_close]
            in_string = False
            escape = False

            for i in range(start + 1, len(s)):
                ch = s[i]
                if in_string:
                    if escape:
                        escape = False
                        continue
                    if ch == "\\":
                        escape = True
                        continue
                    if ch == '"':
                        in_string = False
                    continue

                # not in string
                if ch == '"':
                    in_string = True
                    continue
                if ch in ("[", "{"):
                    stack.append(matching[ch])
                    continue
                if ch == "]" or ch == "}":
                    if not stack:
                        break
                    top = stack.pop()
                    if ch != top:
                        # mismatch; give up
                        return None
                    if not stack:
                        return s[start : i + 1]

            return None

        extracted = _extract_balanced_json_substring(text)
        if extracted:
            return extracted.strip()
        
        # If no code block found, return the original text
        return text.strip()
    
    def _parse_json(self, text: str) -> Any:
        """
        Parse JSON string, handling various formats.
        """
        # Extract JSON from markdown if present
        json_text = self._extract_json_from_markdown(text)

        def _normalize(s: str) -> list[str]:
            # Produce candidate strings that are more likely parseable.
            cands: list[str] = [s]
            try:
                cands.append(
                    s.replace("\\n", "\n")
                    .replace("\\r", "\r")
                    .replace("\\t", "\t")
                )
            except Exception:
                pass
            try:
                # Convert escaped quotes: \" -> "
                cands.append(s.replace(r'\\"', '"').replace(r'\"', '"'))
            except Exception:
                pass
            try:
                decoded = bytes(s, "utf-8").decode("unicode_escape")
                cands.append(decoded)
            except Exception:
                pass

            # Deduplicate preserving order
            out: list[str] = []
            seen: set[str] = set()
            for x in cands:
                if x not in seen:
                    out.append(x)
                    seen.add(x)
            return out

        def _escape_literal_newlines_in_json_strings(s: str) -> str:
            """Fix invalid JSON where LLM includes literal newlines inside string values.

            JSON allows newlines in strings only as escaped sequences (\n). When an LLM
            outputs JSON-like text, it sometimes contains actual newline characters
            between the quotes, which breaks json.loads.

            We escape only newlines/tabs/carriage returns that appear *inside* double quotes.
            """

            # NOTE: We must correctly handle escaped quotes with multiple backslashes.
            # Simple "escape" boolean breaks for sequences like: \\\" (escaped backslash + escaped quote).
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

                # in_string
                if ch == '\\':
                    backslash_run += 1
                    out.append(ch)
                    continue

                # If we see a quote and the number of consecutive backslashes
                # immediately before it is even => it terminates the string.
                if ch == '"':
                    if backslash_run % 2 == 0:
                        in_string = False
                    backslash_run = 0
                    out.append(ch)
                    continue

                # Reset backslash run for any non-backslash char.
                backslash_run = 0

                if ch == '\n':
                    out.append('\\n')
                elif ch == '\r':
                    out.append('\\r')
                elif ch == '\t':
                    out.append('\\t')
                elif ch == '\u2028' or ch == '\u2029':
                    # JSON doesn't allow these raw line separators in strings.
                    out.append('\\n')
                else:
                    out.append(ch)

            return ''.join(out)

        def _try_load_variants(candidate: str) -> Any | None:
            """Try multiple lightweight unescaping variants before json.loads."""

            repaired = _escape_literal_newlines_in_json_strings(candidate)

            def _normalize_stray_double_commas(s: str) -> str:
                """Fix cases like: ...",\n,\n"children": ...

                LLMs occasionally emit an extra comma token on its own line.
                We remove a second comma when it is immediately preceded by a comma
                and followed by a JSON value boundary (quote/array/object/} or ]).
                """

                # Example: ",\s*,\s*\"children\"" -> ",\"children\""
                return re.sub(
                    r",\s*,(?=\s*(\"|\{|\[|\]|\}))",
                    ",",
                    s,
                )

            def _remove_standalone_comma_lines(s: str) -> str:
                """Remove lines that contain only a comma.

                Example artifact from some LLM outputs:
                  "...",
                  ,
                  "children": [...]

                After escaping literal newlines inside strings, such comma-lines
                should be outside quotes, so removing them is safe-ish and fixes
                invalid JSON.
                """

                # Multiline, remove lines like: "," or ",   " or "   ,"
                return re.sub(r"(?m)^[ \t]*,[ \t]*$", "", s)

            def _remove_standalone_closing_bracket_before_object(s: str) -> str:
                """Remove a stray standalone `]` line directly before `}`.

                Example bad artifact:
                  "children": [ ... ]
                	]   <- extra
                	},

                Expected:
                  "children": [ ... ]
                	},

                This fixes some LLM outputs that add one extra closing bracket.
                """

                # Support both LF and CRLF newlines.
                return re.sub(
                    r"(?m)^[ \t]*\][ \t]*$\r?\n(?=[ \t]*\})",
                    "",
                    s,
                )

            def _remove_double_closing_bracket_before_object(s: str) -> str:
                """Fix pattern: ... ] ] } ...

                Some LLM outputs insert an extra closing bracket right after
                closing an inner array, before an object closes.
                """

                # If we have: ]   ]   }  => remove the second ]
                return re.sub(r"\]\s*\]\s*(?=\})", "]", s)

            repaired = _normalize_stray_double_commas(repaired)
            repaired = _remove_standalone_comma_lines(repaired)
            repaired = _remove_standalone_closing_bracket_before_object(repaired)
            repaired = _remove_double_closing_bracket_before_object(repaired)
            variants: list[str] = [repaired]

            # normalize trailing commas
            try:
                variants.append(re.sub(r",\s*([}\]])", r"\1", repaired))
            except Exception:
                pass

            # unescape common escaped quotes
            try:
                variants.append(repaired.replace(r'\\"', '"').replace(r'\"', '"'))
            except Exception:
                pass

            # dedupe
            uniq: list[str] = []
            seen: set[str] = set()
            for v in variants:
                if v not in seen:
                    uniq.append(v)
                    seen.add(v)

            for v in uniq:
                try:
                    return json.loads(v)
                except Exception:
                    continue
            return None

        def _attempt_parse(s: str) -> Any | None:
            # 1) direct parse
            direct = _try_load_variants(s)
            if direct is not None:
                return direct

            # 2) find array/object substring and parse
            array_match = re.search(r'\[[\s\S]*\]', s)
            if array_match:
                arr = array_match.group(0)
                parsed = _try_load_variants(arr)
                if parsed is not None:
                    return parsed

            object_match = re.search(r'\{[\s\S]*\}', s)
            if object_match:
                obj = object_match.group(0)
                parsed = _try_load_variants(obj)
                if parsed is not None:
                    return parsed

            return None

        for cand in _normalize(json_text):
            parsed = _attempt_parse(cand)
            if parsed is not None:
                return parsed

        # Last-resort fallback: parse first JSON array/object directly from the original input.
        # This helps when markdown extraction fails and leaves code fences or extra text.
        try:
            # Use balanced extraction instead of first/last indices.
            open_idx_arr = text.find("[")
            open_idx_obj = text.find("{")
            open_idx_candidates = [i for i in (open_idx_arr, open_idx_obj) if i != -1]
            if open_idx_candidates:
                start = min(open_idx_candidates)
                start_ch = text[start]
                matching = {"[": "]", "{": "}"}
                expected_close = matching[start_ch]
                stack: list[str] = [expected_close]
                in_string = False
                escape = False
                end_idx: int | None = None
                for i in range(start + 1, len(text)):
                    ch = text[i]
                    if in_string:
                        if escape:
                            escape = False
                            continue
                        if ch == "\\":
                            escape = True
                            continue
                        if ch == '"':
                            in_string = False
                        continue

                    if ch == '"':
                        in_string = True
                        continue
                    if ch in ("[", "{"):
                        stack.append(matching[ch])
                        continue
                    if ch == "]" or ch == "}":
                        if not stack:
                            break
                        top = stack.pop()
                        if ch != top:
                            break
                        if not stack:
                            end_idx = i
                            break

                if end_idx is not None:
                    candidate_src = text[start : end_idx + 1]
                    parsed = _try_load_variants(candidate_src)
                    if parsed is not None:
                        return parsed
        except Exception:
            pass

        # Return original text if parsing fails
        return json_text
    
    async def run(self, context: Context) -> Context:
        """
        Execute JSON parsing.
        
        Reads from context[input_key], parses JSON, writes to context[output_key].
        """
        input_key = self.get_config("input_key")
        output_key = self.get_config("output_key", "parsed_json")
        default_on_error = self.get_config("default_on_error", None)
        
        if not input_key:
            raise ValueError("JsonParseNode requires 'input_key' in config")
        
        input_text = context.get(input_key)
        
        if input_text is None:
            if default_on_error is not None:
                context.set(output_key, default_on_error)
            else:
                raise ValueError(f"Input key '{input_key}' not found in context")
            return context
        
        try:
            parsed = self._parse_json(input_text)
            context.set(output_key, parsed)
        except Exception as e:
            if default_on_error is not None:
                context.set(output_key, default_on_error)
            else:
                raise ValueError(f"Failed to parse JSON from '{input_key}': {str(e)}")
        
        return context


class JsonTransformNode(BaseNode):
    """
    Node that transforms parsed JSON into structure format for LMS.
    
    Converts from:
    [
      {"title": "Topic", "description": "...", "children": [...]}
    ]
    
    To:
    [
      {"id": "uuid", "title": "Topic", "type": "topic", "children": [...]}
    ]
    
    Configuration:
        input_key: Key in context containing the JSON array (required)
        output_key: Key to store transformed structure (default: "structure")
        default_type: Type to use for nodes (default: "topic")
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(name or "JsonTransformNode", config)
    
    def _transform_item(self, item: Dict[str, Any], default_type: str = "topic") -> Dict[str, Any]:
        """
        Transform a single item to include id and type.
        """
        import uuid
        
        result = {
            "id": str(uuid.uuid4()),
            "title": item.get("title", "Untitled"),
            "type": item.get("type", default_type),
        }
        
        # Include description if present
        if "description" in item:
            result["description"] = item["description"]
        
        # Transform children recursively
        if "children" in item and isinstance(item["children"], list):
            result["children"] = [
                self._transform_item(child, "theory") 
                for child in item["children"]
            ]
        
        return result

    async def run(self, context: Context) -> Context:
        """Execute JSON transformation."""
        input_key = self.get_config("input_key")
        output_key = self.get_config("output_key", "structure")
        default_type = self.get_config("default_type", "topic")

        if not input_key:
            raise ValueError("JsonTransformNode requires 'input_key' in config")

        input_data = context.get(input_key)
        if input_data is None:
            raise ValueError(f"Input key '{input_key}' not found in context")

        def _coerce_dict_to_list(obj: Dict[str, Any]) -> list[Any]:
            for k in ("structure", "topics", "outline", "course_outline", "items"):
                inner = obj.get(k)
                if isinstance(inner, list):
                    return inner

            # Single topic object
            if "title" in obj or "children" in obj or "description" in obj:
                return [obj]

            raise ValueError(
                f"Unsupported dict shape for '{input_key}'. Keys={list(obj.keys())}"
            )

        def _normalize_near_json(s: str) -> str:
            # Remove trailing commas before } or ]
            return re.sub(r",\s*([}\]])", r"\1", s)

        def _escape_literal_newlines_in_json_strings(s: str) -> str:
            """Escape actual newline characters inside JSON string literals.

            LLMs sometimes produce JSON-like text where a string value contains
            literal newlines (not "\\n"). json.loads then fails.

            This converts literal newlines/tabs/carriage returns *inside* quoted
            strings into escaped sequences (\\n/\\t/\\r).
            """

            # NOTE: must handle escaped quotes correctly.
            # We treat a quote as terminating a JSON string only if it is preceded
            # by an even number of consecutive backslashes.
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

                # reset when we hit a non-backslash char
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

        def _try_json_loads(s: str) -> Any:
            def _normalize_stray_double_commas(s_in: str) -> str:
                return re.sub(
                    r",\s*,(?=\s*(\"|\{|\[|\]|\}))",
                    ",",
                    s_in,
                )

            def _remove_standalone_comma_lines(s_in: str) -> str:
                return re.sub(r"(?m)^[ \t]*,[ \t]*$", "", s_in)

            def _remove_standalone_closing_bracket_before_object(s_in: str) -> str:
                return re.sub(
                    r"(?m)^[ \t]*\][ \t]*$\r?\n(?=[ \t]*\})",
                    "",
                    s_in,
                )

            def _remove_double_closing_bracket_before_object(s_in: str) -> str:
                return re.sub(r"\]\s*\]\s*(?=\})", "]", s_in)

            def _final_unescape_quotes(s_in: str) -> str:
                return s_in.replace(r'\\"', '"').replace(r'\"', '"')

            s2 = _normalize_near_json(s)
            s2 = _escape_literal_newlines_in_json_strings(s2)
            s2 = _normalize_stray_double_commas(s2)
            s2 = _remove_standalone_comma_lines(s2)
            s2 = _remove_standalone_closing_bracket_before_object(s2)
            s2 = _remove_double_closing_bracket_before_object(s2)
            s2 = re.sub(r",\s*([}\]])", r"\1", s2)
            s2 = _final_unescape_quotes(s2)
            return json.loads(s2)

        def _extract_code_block_json(s: str) -> str:
            # prefer first fenced ```json ... ``` block
            fenced = re.findall(r"```(?:json)?\s*\n?(.*?)\n?```", s, flags=re.DOTALL | re.IGNORECASE)
            if fenced:
                return fenced[0].strip()
            return s

        def _extract_json_array_or_object_substring(s: str) -> Any:
            array_match = re.search(r"\[[\s\S]*\]", s)
            if array_match:
                return _try_json_loads(array_match.group(0))
            object_match = re.search(r"\{[\s\S]*\}", s)
            if object_match:
                return _try_json_loads(object_match.group(0))
            raise ValueError("No JSON array/object substring found")

        def _coerce_str_to_list(s: str) -> list[Any]:
            raw = s.strip()
            if not raw:
                return []

            # Candidate texts: original + unicode-unescaped + minimally unescaped
            candidates: list[str] = []

            def _add_candidate(x: str) -> None:
                if x is None:
                    return
                if x not in candidates:
                    candidates.append(x)

            _add_candidate(raw)

            # Very robust fallback: if the string contains JSON array/object,
            # extract the first [ ... ] substring explicitly.
            first_arr = raw.find("[")
            last_arr = raw.rfind("]")
            if first_arr != -1 and last_arr != -1 and last_arr > first_arr:
                arr_src = raw[first_arr : last_arr + 1]
                _add_candidate(arr_src)

            first_obj = raw.find("{")
            last_obj = raw.rfind("}")
            if first_obj != -1 and last_obj != -1 and last_obj > first_obj:
                obj_src = raw[first_obj : last_obj + 1]
                _add_candidate(obj_src)

            _add_candidate(_extract_code_block_json(raw))

            def _manual_unescape(x: str) -> str:
                return (
                    x.replace("\\n", "\n")
                    .replace("\\r", "\r")
                    .replace("\\t", "\t")
                    .replace(r'\\"', '"')
                    .replace(r'\"', '"')
                )

            # Iteratively apply unicode_escape decode + manual unescape.
            # LLM/toolchains may double-escape sequences, so one pass might not be enough.
            cur = raw
            for _ in range(4):
                try:
                    decoded = bytes(cur, "utf-8").decode("unicode_escape")
                except Exception:
                    decoded = cur

                # Always consider decoded and its manual variant.
                _add_candidate(decoded)
                _add_candidate(_extract_code_block_json(decoded))
                try:
                    mu = _manual_unescape(decoded)
                    _add_candidate(mu)
                    _add_candidate(_extract_code_block_json(mu))
                except Exception:
                    pass

                if decoded == cur:
                    break
                cur = decoded

            last_err: str = raw[:200]

            for cand in candidates:
                try:
                    # Try parse as-is
                    parsed = _try_json_loads(cand)
                except Exception:
                    parsed = None

                if parsed is not None:
                    if isinstance(parsed, list):
                        return parsed
                    if isinstance(parsed, dict):
                        return _coerce_dict_to_list(parsed)

                # Try extract array/object substring
                try:
                    parsed2 = _extract_json_array_or_object_substring(cand)
                    if isinstance(parsed2, list):
                        return parsed2
                    if isinstance(parsed2, dict):
                        return _coerce_dict_to_list(parsed2)
                except Exception as e:
                    last_err = str(e)[:200]

            raise ValueError(
                f"Input data for '{input_key}' is a string but cannot be parsed as JSON array/dict. "
                f"Preview={s[:200]!r}"
            )

        def _coerce_to_list(value: Any) -> list[Any]:
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                return _coerce_dict_to_list(value)
            if isinstance(value, str):
                return _coerce_str_to_list(value)
            raise ValueError(
                f"Input data for '{input_key}' must be an array-like JSON value (list/dict/json-string), "
                f"got {type(value).__name__}."
            )

        input_list = _coerce_to_list(input_data)

        # Transform each item
        structure = [self._transform_item(item, default_type) for item in input_list]
        context.set(output_key, structure)
        return context


class ExtractCourseMetadataNode(BaseNode):
    """
    Node that extracts course title and description from the first topic.
    
    Uses the first item in the structure array to set course_title and course_description.
    
    Configuration:
        input_key: Key in context containing the structure array (required)
        title_output_key: Key to store course title (default: "course_title")
        description_output_key: Key to store course description (default: "course_description")
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(name or "ExtractCourseMetadataNode", config)
    
    async def run(self, context: Context) -> Context:
        """
        Extract course metadata from structure.
        """
        input_key = self.get_config("input_key", "structure")
        title_output_key = self.get_config("title_output_key", "course_title")
        description_output_key = self.get_config("description_output_key", "course_description")
        
        structure = context.get(input_key)
        
        if structure and isinstance(structure, list) and len(structure) > 0:
            first_topic = structure[0]
            
            # Use first topic title as course title
            course_title = first_topic.get("title", "Untitled Course")
            context.set(title_output_key, course_title)
            
            # Use first topic description as course description
            course_description = first_topic.get("description", "")
            context.set(description_output_key, course_description)
        else:
            # Default values if no structure
            context.set(title_output_key, "Untitled Course")
            context.set(description_output_key, "")
        
        return context
