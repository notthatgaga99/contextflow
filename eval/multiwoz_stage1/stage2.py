"""Stage-2 answer sufficiency. 4 targets × 3 contexts. llama3.1:8b generate only.

No routing with Ollama. No Vertex. Checkpoint after each case.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

from app.llm.tokens import count as token_count
from eval.multiwoz_stage1.run import STAGE1_CASES, history_and_target, load_map, replay

OUT = Path(__file__).resolve().parent / "stage2.json"
MODEL = "llama3.1:8b"
SYSTEM = (
    "You are a Cambridge tourist-information assistant. "
    "Answer the user's latest message using ONLY the supplied context. "
    "If a fact is missing, say so. Do not invent postcodes, names, or bookings. Be brief."
)

# Strongest natural return/interrupt/copy cases. Not the easy named-only sanity set.
STAGE2_IDS = ["PMUL0079", "MUL2423", "MUL0810", "MUL2053"]

RUBRIC = {
    "PMUL0079": {
        "ok": ["01223316074", "cheap", "guest", "parking", "do not have", "don't have", "unknown", "not given"],
        "bad": ["saigon"],
    },
    "MUL2423": {
        "ok": ["theatre", "theater", "centre", "center", "which", "not specified", "don't know", "several"],
        "bad": [],
        "clarify_ok": True,
    },
    "MUL0810": {
        "ok": ["museum", "technology", "do not have", "don't have", "not given", "unknown"],
        "bad": ["cb58wr", "pizza hut"],
    },
    "MUL2053": {
        "ok": ["tuesday", "tue"],
        "bad": ["wednesday", "monday"],
    },
}


def chat(user: str) -> str:
    last = None
    for attempt in range(3):
        payload = json.dumps({
            "model": MODEL, "stream": False,
            "options": {"temperature": 0.0},
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user},
            ],
        }).encode("utf-8")
        req = urllib.request.Request(
            os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/chat",
            data=payload, headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return str((body.get("message") or {}).get("content") or "")
        except Exception as exc:
            last = exc
            time.sleep(4 * (attempt + 1))
    return f"[ollama error] {last}"


def score(case_id: str, answer: str, clarify: bool) -> dict:
    rub = RUBRIC[case_id]
    low = answer.lower()
    if clarify and rub.get("clarify_ok"):
        return {"answer_correct": True, "note": "CLARIFY ok", "bad": [], "ok": []}
    ok = [k for k in rub["ok"] if k.lower() in low]
    bad = [k for k in rub["bad"] if k.lower() in low]
    return {
        "answer_correct": bool(ok) and not bad,
        "note": "ok" if (ok and not bad) else "miss_or_bad",
        "ok": ok, "bad": bad,
    }


def main() -> int:
    cases_by_id = {c["id"]: c for c in STAGE1_CASES}
    dialogues = load_map()
    payload = {"model": MODEL, "cases": []}
    if OUT.is_file():
        try:
            payload = json.loads(OUT.read_text(encoding="utf-8"))
            payload.setdefault("cases", [])
        except json.JSONDecodeError:
            payload = {"model": MODEL, "cases": []}
    done = {c["id"] for c in payload["cases"]}
    for cid in STAGE2_IDS:
        if cid in done:
            print("skip", cid, flush=True)
            continue
        spec = cases_by_id[cid]
        d = dialogues[spec["dialogue_id"]]
        hist, target = history_and_target(d, spec["target_turn_id"])
        print(f"replay {cid} (no generate)...", flush=True)
        routed = replay(hist, target)
        full_hist = "\n".join(f"{h['speaker']}: {h['text']}" for h in hist)
        contexts = {
            "full_history": full_hist,
            "full_task": routed.get("compiled_full_task") or "(no selected task; CLARIFY)",
            "referent_compact": routed.get("compiled_compact") or "(no selected referent; CLARIFY)",
        }
        row = {
            "id": cid,
            "class": spec["class"],
            "target": target,
            "transition": routed["transition"],
            "task_id": routed["task_id"],
            "referent": routed["predicted_referent_id"],
            "conditions": {},
        }
        for name, ctx in contexts.items():
            print(f"  generate {name}...", flush=True)
            t0 = time.perf_counter()
            if name != "full_history" and routed["transition"] == "CLARIFY" and spec.get("clarify_ok"):
                answer = routed.get("clarify") or "(CLARIFY)"
                elapsed = 0.0
                sc = score(cid, answer, True)
            else:
                prompt = f"CONTEXT:\n{ctx}\n\nLATEST USER MESSAGE:\n{target}\n"
                answer = chat(prompt)
                elapsed = round(time.perf_counter() - t0, 2)
                sc = score(cid, answer, routed["transition"] == "CLARIFY" and spec.get("clarify_ok"))
            row["conditions"][name] = {
                "context_tokens": token_count(ctx),
                "answer": answer,
                "latency_s": elapsed,
                **sc,
            }
        payload["cases"].append(row)
        OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print("checkpoint", cid, flush=True)
    print("wrote", OUT, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
