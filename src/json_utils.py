"""
Shared helper for tolerantly parsing JSON out of LLM responses.

Small local models sometimes wrap JSON in ```json code fences or add a
stray sentence despite being told not to — this centralizes the
cleanup so every agent that needs structured output handles it the
same way.
"""
from __future__ import annotations

import json
import re


def extract_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    return json.loads(cleaned)
