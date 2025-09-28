from __future__ import annotations

import re
from unidecode import unidecode


RE_SPACES = re.compile(r"\s+")
RE_NON_ALNUM = re.compile(r"[^a-z0-9 ]")
RE_NUMS = re.compile(r"\d+")


def normalize_text(s: str) -> str:
    s2 = unidecode(s or "").lower()
    s2 = RE_NON_ALNUM.sub(" ", s2)
    s2 = RE_SPACES.sub(" ", s2).strip()
    return s2


def extract_numbers(s: str) -> list[str]:
    return RE_NUMS.findall(s or "")
