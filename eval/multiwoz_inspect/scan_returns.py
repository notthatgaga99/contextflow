"""Inspect MultiWOZ 2.2 test slice for genuine returns. No engine."""
from __future__ import annotations

import json
import re
from pathlib import Path

DATA = Path("data/multiwoz/dialogues_001.json")

CLOSE = re.compile(
    r"\b(thank|thanks|goodbye|bye|that('s| is) all|that was (it|all)|that will be all|"
    r"that is everything|have a (nice|great) day|no more|nothing else|covers it)\b",
    re.I,
)
ALSO_NEED = re.compile(
    r"\b(i (also )?need (to )?(book |find )?(a )?(train|taxi|hotel|restaurant|attraction))\b",
    re.I,
)


def load():
    return json.loads(DATA.read_text(encoding="utf-8"))


def frames_summary(turn):
    out = []
    for fr in turn.get("frames") or []:
        st = fr.get("state") or {}
        intent = st.get("active_intent")
        req = st.get("requested_slots") or []
        slots = list((st.get("slot_values") or {}).keys())
        copies = [s.get("copy_from") for s in (fr.get("slots") or []) if s.get("copy_from")]
        if intent not in (None, "NONE", "") or slots or req or copies:
            out.append((fr["service"], intent, req, slots[:8], copies))
    return out


def dump(data, did: str) -> None:
    d = next(x for x in data if x["dialogue_id"] == did)
    print("\n==========", did, d["services"])
    for t in d["turns"]:
        u = t["utterance"].replace("\n", " ")
        print(f"{t['turn_id']:>2} {t['speaker']:7} {u[:170]}")
        if t["speaker"] == "USER":
            fs = frames_summary(t)
            if fs:
                print("         frames", fs)


def main() -> None:
    data = load()
    candidates = []
    for d in data:
        if len(d.get("services") or []) < 2:
            continue
        seq = []
        for t in d["turns"]:
            if t["speaker"] != "USER":
                continue
            prim = None
            for fr in t.get("frames") or []:
                st = fr.get("state") or {}
                if st.get("active_intent") not in (None, "NONE", ""):
                    prim = fr["service"]
                    break
            seq.append((int(t["turn_id"]), prim, t["utterance"]))
        for i, (tid, svc, utt) in enumerate(seq):
            if svc is None or CLOSE.search(utt):
                continue
            firsts = [j for j, (_a, s, _u) in enumerate(seq) if s == svc]
            if not firsts or firsts[0] == i:
                continue
            first = firsts[0]
            mid = [seq[j][1] for j in range(first + 1, i) if seq[j][1]]
            if not any(s and s != svc for s in mid):
                continue
            if ALSO_NEED.search(utt) and "before we" not in utt.lower():
                continue
            candidates.append((d["dialogue_id"], tid, svc, mid, utt))

    print("non-closing A-B-A excluding also-need", len(candidates))
    for c in candidates:
        print(c[0], "t", c[1], "A", c[2], "mid", c[3])
        print(" ", c[4][:240])

    ids = [
        "PMUL0079.json",
        "PMUL4247.json",
        "PMUL4440.json",
        "PMUL4643.json",
        "PMUL2477.json",
        "PMUL2719.json",
        "PMUL4660.json",
        "MUL0071.json",
        "PMUL3858.json",
    ]
    for did in ids:
        try:
            dump(data, did)
        except StopIteration:
            print("missing", did)


if __name__ == "__main__":
    main()
