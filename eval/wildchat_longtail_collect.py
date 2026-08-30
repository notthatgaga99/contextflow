"""Collect first N WildChat conversations with turn>=10. Stream only. No engine."""

from __future__ import annotations

import json
from pathlib import Path

from datasets import load_dataset

N = 80
MIN_TURNS = 10
OUT = Path("data/wildchat/longtail80.json")


def user_texts(conv: list) -> list[str]:
    out = []
    for u in conv or []:
        if (u.get("role") or "").lower() == "user":
            t = (u.get("content") or "").replace("\n", " ").strip()
            out.append(t)
    return out


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    ds = load_dataset("allenai/WildChat", split="train", streaming=True)
    kept = []
    scanned = 0
    skipped_short = 0
    skipped_lang = 0
    skipped_toxic = 0
    skipped_empty = 0
    for row in ds:
        scanned += 1
        turn = int(row.get("turn") or 0)
        if turn < MIN_TURNS:
            skipped_short += 1
            continue
        if row.get("toxic"):
            skipped_toxic += 1
            continue
        lang = (row.get("language") or "").strip()
        if lang and lang.lower() not in ("english", "en"):
            skipped_lang += 1
            continue
        users = user_texts(row.get("conversation") or [])
        if len(users) < MIN_TURNS:
            skipped_empty += 1
            continue
        if sum(1 for u in users if not u) > 2:
            skipped_empty += 1
            continue
        kept.append({
            "conversation_hash": row.get("conversation_hash") or row.get("conversation_id"),
            "model": row.get("model"),
            "turn": turn,
            "n_user": len(users),
            "language": lang,
            "redacted": bool(row.get("redacted")),
            "timestamp": str(row.get("timestamp")),
            "user_texts": users,
        })
        print(f"kept {len(kept)}/{N} scanned={scanned} turn={turn} users={len(users)}", flush=True)
        if len(kept) >= N:
            break
        if scanned >= 25000:
            break
    OUT.write_text(json.dumps({
        "dataset": "allenai/WildChat",
        "license": "ODC-BY",
        "procedure": (
            "HF streaming split=train, first 80 with turn>=10, language English, "
            "toxic!=True, >=10 non-empty-enough user utterances. Order = stream order, not CF-favor."
        ),
        "scanned": scanned,
        "skipped_short": skipped_short,
        "skipped_lang": skipped_lang,
        "skipped_toxic": skipped_toxic,
        "skipped_empty": skipped_empty,
        "n_kept": len(kept),
        "conversations": kept,
    }, indent=2), encoding="utf-8")
    print("wrote", OUT, "kept", len(kept), "scanned", scanned)


if __name__ == "__main__":
    main()
