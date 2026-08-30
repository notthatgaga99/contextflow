import json
from pathlib import Path

data = json.loads(Path("data/multiwoz/dialogues_001.json").read_text(encoding="utf-8"))
ids = [
    "PMUL0079.json",
    "MUL0810.json",
    "PMUL4186.json",
    "MUL2053.json",
    "MUL2423.json",
    "PMUL2882.json",
    "MUL0789.json",
    "MUL0088.json",
    "PMUL2746.json",
    "PMUL4842.json",
    "MUL0089.json",
    "PMUL0204.json",
]


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


for did in ids:
    d = next((x for x in data if x["dialogue_id"] == did), None)
    if not d:
        print("MISSING", did)
        continue
    print("\n==========", did, d["services"])
    for t in d["turns"]:
        u = t["utterance"].replace("\n", " ")
        print(f"{t['turn_id']:>2} {t['speaker']:7} {u[:175]}")
        if t["speaker"] == "USER":
            fs = frames_summary(t)
            if fs:
                print("         frames", fs)
