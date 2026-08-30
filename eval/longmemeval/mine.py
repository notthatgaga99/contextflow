"""Mine LongMemEval user turns for routing-like phenomena. No engine. No gold."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

DEICTIC = re.compile(
    r"\b(that|this|it|those|these|the other (one|thing)|the first one|the second one)\b",
    re.I,
)
FIX_THAT = re.compile(r"\b(fix that|change this|what about that|back to that|the other one)\b", re.I)
CORRECTION = re.compile(
    r"\b(no,?\s+(the other|I meant|not that)|actually,?\s+|wait[,.]|never mind|nvm)\b",
    re.I,
)
RESUME = re.compile(
    r"\b(going back|go back to|as I (said|mentioned)|remember when|what did we (decide|say)|continue where)\b",
    re.I,
)
QUESTION = re.compile(r"\?\s*$")


def load(path: Path) -> list:
    return json.loads(path.read_text(encoding="utf-8"))


def user_turns(session: list) -> list[dict]:
    return [t for t in session if t.get("role") == "user"]


def scan_instance(inst: dict, source: str) -> list[dict]:
    rows = []
    qid = inst["question_id"]
    qtype = inst["question_type"]
    sessions = inst["haystack_sessions"]
    sids = inst.get("haystack_session_ids") or [f"{qid}:s{i}" for i in range(len(sessions))]
    for si, sess in enumerate(sessions):
        sid = sids[si] if si < len(sids) else f"{qid}:s{si}"
        for ti, turn in enumerate(sess):
            if turn.get("role") != "user":
                continue
            text = turn.get("content") or ""
            flags = []
            if FIX_THAT.search(text):
                flags.append("deixis_strong")
            if DEICTIC.search(text) and len(text) < 220:
                flags.append("deixis")
            if CORRECTION.search(text):
                flags.append("correction")
            if RESUME.search(text):
                flags.append("resumption")
            if "has_answer" in turn and turn.get("has_answer"):
                flags.append("has_answer")
            if not flags:
                continue
            rows.append({
                "source": source,
                "question_id": qid,
                "question_type": qtype,
                "session_id": sid,
                "session_index": si,
                "turn_index": ti,
                "n_sessions": len(sessions),
                "n_turns_in_session": len(sess),
                "text": text,
                "flags": flags,
                "is_abs": str(qid).endswith("_abs"),
            })
    return rows


def main() -> None:
    oracle_p = Path("data/longmemeval/longmemeval_oracle.json")
    s_p = Path("data/longmemeval/longmemeval_s_cleaned.json")
    out_dir = Path("eval/longmemeval")
    out_dir.mkdir(parents=True, exist_ok=True)

    oracle = load(oracle_p)
    rows = []
    for inst in oracle:
        rows.extend(scan_instance(inst, "oracle"))

    print("oracle instances", len(oracle), "flagged user turns", len(rows))
    print("flag counts", Counter(f for r in rows for f in r["flags"]))
    print("deixis_strong", sum(1 for r in rows if "deixis_strong" in r["flags"]))
    print("correction", sum(1 for r in rows if "correction" in r["flags"]))
    print("resumption", sum(1 for r in rows if "resumption" in r["flags"]))

    # print samples
    for kind in ("deixis_strong", "correction", "resumption"):
        print("\n====", kind)
        n = 0
        for r in rows:
            if kind in r["flags"]:
                print(r["question_id"], r["session_index"], r["text"][:240].replace("\n", " "))
                n += 1
                if n >= 12:
                    break

    # within-session topic: consecutive user msgs jaccard
    print("\n==== sample full evidence session (first inst)")
    inst = oracle[0]
    for si, sess in enumerate(inst["haystack_sessions"]):
        print(f"\n-- session {si} {inst['haystack_session_ids'][si]} --")
        for t in sess:
            role = t["role"]
            c = (t["content"] or "").replace("\n", " ")[:180]
            print(f"  {role}: {c}")

    if s_p.exists() and s_p.stat().st_size > 1_000_000:
        print("\nS file present", s_p.stat().st_size)
    else:
        print("\nS file not ready")


if __name__ == "__main__":
    main()
