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
    import json, re
    try:
        data = json.loads(text)
    except Exception:
        m = re.search(r"\[.*\]", text, flags=re.S)
        data = json.loads(m.group(0)) if m else []
    if not isinstance(data, list):
        data = [data]
    return data[:max_items]
