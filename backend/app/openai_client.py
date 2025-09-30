from __future__ import annotations

import logging
from typing import Any

from .config import settings

try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # type: ignore

log = logging.getLogger("app.openai")


def suggest_with_openai(prompt: str, max_items: int = 3) -> list[dict[str, Any]]:
    if not settings.OPENAI_API_KEY or OpenAI is None:
        raise RuntimeError("OPENAI_DISABLED")

    client = OpenAI(api_key=settings.OPENAI_API_KEY)  # type: ignore
    model = settings.AI_MODEL
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a meticulous data matching assistant. Reply in strict JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    text = resp.choices[0].message.content or "[]"
    print(f"OpenAI raw response: {text[:500]}...")  # Log first 500 chars
    
    import json, re
    try:
        data = json.loads(text)
        print(f"OpenAI parsed JSON successfully: {len(data) if isinstance(data, list) else 1} items")
    except Exception as e:
        print(f"OpenAI JSON parse error: {e}")
        m = re.search(r"\[.*\]", text, flags=re.S)
        data = json.loads(m.group(0)) if m else []
        print(f"OpenAI regex fallback result: {data}")
    if not isinstance(data, list):
        data = [data]
    print(f"OpenAI final result: {len(data)} items")
    return data[:max_items]
