from __future__ import annotations

import json
import re
from typing import Any, Iterable


CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
LATIN_RE = re.compile(r"[A-Za-z]")


def _iter_text(value: Any) -> Iterable[str]:
    if value is None:
        return
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _iter_text(item)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_text(item)
        return
    try:
        yield json.dumps(value, ensure_ascii=False)
    except Exception:
        yield str(value)


def infer_response_language(payload: Any, default: str = "English") -> str:
    text = "\n".join(_iter_text(payload))
    if not text.strip():
        return default

    cjk_count = len(CJK_RE.findall(text))
    latin_count = len(LATIN_RE.findall(text))
    if cjk_count >= 2 or (cjk_count > 0 and cjk_count >= latin_count * 0.08):
        return "Simplified Chinese"
    return default


def build_language_instruction(payload: Any) -> str:
    language = infer_response_language(payload)
    if language == "Simplified Chinese":
        return """

Output language policy:
- The learner's dominant input language is Simplified Chinese.
- Write every learner-facing natural-language value in Simplified Chinese.
- Keep JSON keys, required schema names, enum values, IDs, booleans, numbers, and option labels exactly as specified.
- Keep conventional technical terms, code, formulas, library names, and API names unchanged when translating them would reduce clarity.
""".rstrip()

    return """

Output language policy:
- Write learner-facing natural-language values in English unless the learner's latest input clearly uses another language.
- Keep JSON keys, required schema names, enum values, IDs, booleans, numbers, and option labels exactly as specified.
""".rstrip()
