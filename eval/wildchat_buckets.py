"""Coarse user-turn buckets for WildChat sample. Not CF gold."""
from __future__ import annotations

import json
import re
from pathlib import Path

p = json.loads(Path("data/wildchat/longtail80.json").read_text(encoding="utf-8"))

RULES = [
    ("code", r"\b(python|javascript|typescript|java\b|c\+\+|c#|sql|html|css|json\.parse|function |class |github|linux|firefox|gradio|debug|error|compiler|api|regex)\b"),
    ("homework", r"\b(oxidant|voltaic|half-reaction|multiple choice|true false|exam|homework|quiz)\b"),
    ("ecommerce", r"\b(lazada|shopify|keyword|product listing|search volume|ecommerce)\b"),
    ("roleplay", r"\b(act as|you are a |jailbreak|dan mode|ignore previous)\b"),
    ("writing", r"\b(rewrite|essay|story|poem|blog|screenplay|summarize)\b"),
    ("travel", r"\b(hotel|flight|itinerary|visa|airport|vacation|tourism)\b"),
    ("clothing", r"\b(dress|outfit|wear |clothing|shoes|fashion|navy|suit)\b"),
    ("food", r"\b(recipe|cook|ingredient|restaurant|meal)\b"),
    ("health", r"\b(symptom|doctor|diagnos|medication|pain)\b"),
    ("translate", r"\b(translate|in chinese|in spanish|in french)\b"),
    ("image", r"\b(midjourney|prompt for|dall-e|stable diffusion)\b"),
    ("math", r"\b(equation|integral|matrix|theorem|prove that)\b"),
]


def bucket(text: str) -> str:
    t = text.lower()
    hits = [name for name, pat in RULES if re.search(pat, t, re.I)]
    if not hits:
        return "other"
    return hits[0]


rows = []
for i, c in enumerate(p["conversations"]):
    seq = [bucket(t) for t in c["user_texts"]]
    distinct = []
    for b in seq:
        if not distinct or distinct[-1] != b:
            distinct.append(b)
    uniq = list(dict.fromkeys(seq))
    # A..X..A with some other in between
    aba = False
    for a_i, a in enumerate(seq):
        later = [j for j in range(a_i + 1, len(seq)) if seq[j] == a]
        if not later:
            continue
        mid = seq[a_i + 1 : later[0]]
        if any(x != a and x != "other" for x in mid):
            aba = True
            break
    rows.append((i, c["n_user"], uniq, distinct[:12], aba, str(c["conversation_hash"])[:16]))

print("sessions with >=3 unique buckets", sum(1 for r in rows if len(r[2]) >= 3))
print("sessions with >=2 unique buckets", sum(1 for r in rows if len(r[2]) >= 2))
print("heuristic ABA", sum(1 for r in rows if r[4]))
print()
for r in rows:
    if len(r[2]) >= 2 or r[4]:
        print(f"{r[0]:02d} n={r[1]} uniq={r[2]} aba={r[4]} {r[5]}")
