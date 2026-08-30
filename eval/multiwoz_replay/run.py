"""Local MultiWOZ replay experiment. Eval-only. Does not import-patch production algorithms.

Usage (from git root):
  python -m eval.multiwoz_replay.run

Requires local Ollama llama3.1:8b. No Vertex.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from pathlib import Path

from app.config import SETTINGS
from app.engine import Engine
from app.llm.ollama import OllamaLLM
from app.llm.tokens import count as token_count
from app.memory.registry import InMemoryRegistry
from eval.multiwoz_replay.cases import CASES, JACCARD_M, RECENCY_K

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "multiwoz" / "dialogues_001.json"
OUT_DIR = Path(__file__).resolve().parent
ANSWER_MODEL = "llama3.1:8b"
ANSWER_SYSTEM = (
    "You are a Cambridge tourist-information assistant. "
    "Answer the user's latest message using ONLY the supplied context. "
    "If a name, postcode, day, or amenity is not in the context, say you do not have that fact. "
    "Do not invent venues, postcodes, or bookings. Be brief."
)


class ProposeOnlyLLM:
    """Ollama propose/embed; generate skipped during history replay."""

    def __init__(self, inner: OllamaLLM):
        self.inner = inner
        self.generate_enabled = False

    def propose(self, prompt: str, schema: dict) -> dict:
        return self.inner.propose(prompt, schema)

    def generate(self, prompt: str) -> str:
        if not self.generate_enabled:
            return ""
        return self.inner.generate(prompt)

    def embed(self, texts: list[str]):
        return self.inner.embed(texts)


def load_dialogues() -> dict:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    return {d["dialogue_id"]: d for d in data}


def transcript_before_target(dialogue: dict, target_id: int) -> list[dict]:
    rows = []
    for t in dialogue["turns"]:
        tid = int(t["turn_id"])
        if tid >= target_id:
            break
        rows.append({
            "turn_id": tid,
            "speaker": t["speaker"],
            "text": t["utterance"].replace("\n", " ").strip(),
        })
    return rows


def target_user(dialogue: dict, target_id: int) -> str:
    for t in dialogue["turns"]:
        if int(t["turn_id"]) == target_id:
            return t["utterance"].replace("\n", " ").strip()
    raise KeyError(target_id)


def format_turns(turns: list[dict]) -> str:
    lines = []
    for t in turns:
        lines.append(f"{t['turn_id']} {t['speaker']}: {t['text']}")
    return "\n".join(lines)


def wordset(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def jaccard(a: str, b: str) -> float:
    sa, sb = wordset(a), wordset(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def recency_context(history: list[dict]) -> str:
    return format_turns(history[-RECENCY_K:])


def jaccard_context(history: list[dict], target: str) -> str:
    ranked = sorted(history, key=lambda t: jaccard(t["text"], target), reverse=True)
    picked = ranked[:JACCARD_M]
    picked.sort(key=lambda t: t["turn_id"])
    return format_turns(picked)


def ollama_chat(model: str, system: str, user: str, timeout_s: float = 300.0) -> str:
    last_exc: Exception | None = None
    for attempt in range(4):
        payload = json.dumps({
            "model": model,
            "stream": False,
            "options": {"temperature": 0.0},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }).encode("utf-8")
        req = urllib.request.Request(
            os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return str((body.get("message") or {}).get("content") or "")
        except Exception as exc:
            last_exc = exc
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"ollama_chat_failed:{last_exc}") from last_exc


def llm_select_context(history: list[dict], target: str) -> str:
    numbered = format_turns(history)
    prompt = (
        "Select earlier turns that are needed to answer the latest user message. "
        "Return JSON only: {\"turn_ids\": [integers]}. Use turn_id values from the list. "
        "If unsure, include the most relevant few turns.\n\n"
        f"HISTORY:\n{numbered}\n\nLATEST USER MESSAGE:\n{target}\n"
    )
    raw = ollama_chat(
        ANSWER_MODEL,
        "Return only JSON. Do not answer the user yet.",
        prompt,
    )
    ids: list[int] = []
    try:
        start, end = raw.find("{"), raw.rfind("}")
        parsed = json.loads(raw[start:end + 1] if start >= 0 else raw)
        ids = [int(x) for x in (parsed.get("turn_ids") or [])]
    except (json.JSONDecodeError, TypeError, ValueError):
        ids = []
    by_id = {t["turn_id"]: t for t in history}
    picked = [by_id[i] for i in ids if i in by_id]
    if not picked:
        picked = history[-RECENCY_K:]
    picked.sort(key=lambda t: t["turn_id"])
    return format_turns(picked)


def ingest_system(reg: InMemoryRegistry, text: str, turn: int) -> None:
    """Eval-only: attach wizard text to the currently active card. Not DST. Not production."""
    del turn
    active = reg.active()
    if active is None:
        return
    snippet = f"SYSTEM: {text}"
    if snippet not in active.anchor.open_loops:
        reg.apply_update(active.id, {"open_loops": [snippet]})
        if text not in active.anchor.decisions:
            # keep a short cue list for retrieval without changing scorer code
            cues = [w for w in wordset(text) if len(w) >= 4][:6]
            for c in cues:
                if c not in active.retrieval_cues:
                    active.retrieval_cues.append(c)


def snapshot_registry(reg: InMemoryRegistry) -> list[dict]:
    rows = []
    for t in reg.open_tasks():
        rows.append({
            "id": t.id,
            "title": t.title,
            "status": t.status,
            "goal": t.anchor.goal,
            "open_loops": list(t.anchor.open_loops),
            "mention_turn": t.mention_turn,
            "last_active_turn": t.last_active_turn,
            "cues": list(t.retrieval_cues),
        })
    return rows


def replay_cf(history: list[dict], target: str, llm: ProposeOnlyLLM) -> dict:
    reg = InMemoryRegistry()
    eng = Engine(llm, reg, SETTINGS, mode="split")
    llm.generate_enabled = False
    replay_log = []
    for t in history:
        if t["speaker"] == "USER":
            print(f"    CF user turn {t['turn_id']} propose...", flush=True)
            t0 = time.perf_counter()
            res = eng.handle_turn(t["text"], t["turn_id"] + 1)
            print(
                f"    CF user turn {t['turn_id']} -> {res.transition.value} "
                f"task={res.task_id} ({time.perf_counter()-t0:.1f}s)",
                flush=True,
            )
            replay_log.append({
                "turn_id": t["turn_id"],
                "transition": res.transition.value,
                "task_id": res.task_id,
                "referent": res.predicted_referent_id,
                "clarify": res.clarify_question,
            })
        else:
            ingest_system(reg, t["text"], t["turn_id"])
    pre_cards = snapshot_registry(reg)
    llm.generate_enabled = False  # answer generated outside engine with shared prompt
    print("    CF target propose...", flush=True)
    t0 = time.perf_counter()
    res = eng.handle_turn(target, history[-1]["turn_id"] + 2 if history else 1)
    print(
        f"    CF target -> {res.transition.value} task={res.task_id} "
        f"({time.perf_counter()-t0:.1f}s)",
        flush=True,
    )
    pkg = res.package
    compiled = ""
    if pkg is not None:
        compiled = eng.compiler.render(pkg)
    selected_blob = compiled + " " + " ".join(
        json.dumps(c) for c in snapshot_registry(reg)
    )
    return {
        "transition": res.transition.value,
        "task_id": res.task_id,
        "predicted_task_id": res.predicted_task_id,
        "predicted_referent_id": res.predicted_referent_id,
        "clarify_question": res.clarify_question,
        "compiled": compiled,
        "answer_tokens": pkg.answer_tokens if pkg else 0,
        "decision_tokens": pkg.decision_tokens if pkg else 0,
        "proposal": dict(llm.inner.last_proposal or {}),
        "replay_log": replay_log,
        "cards_before_target": pre_cards,
        "cards_after_target": snapshot_registry(reg),
        "selected_blob": selected_blob,
        "evidence": dict(res.resolution_evidence or {}),
        "top_raw": res.decision.top_raw,
        "raw_margin": res.decision.raw_margin,
    }


def generate_answer(context: str, target: str) -> str:
    user = (
        f"CONTEXT:\n{context}\n\n"
        f"LATEST USER MESSAGE:\n{target}\n\n"
        "Answer the latest user message."
    )
    return ollama_chat(ANSWER_MODEL, ANSWER_SYSTEM, user)


def contains_any(text: str, needles: list[str]) -> bool:
    low = text.lower()
    return any(n.lower() in low for n in needles if n)


def score_selection(case: dict, blob: str, transition: str | None = None) -> dict:
    blob_l = blob.lower()
    hits = [k for k in case.get("selection_any") or [] if k.lower() in blob_l]
    avoid = [k for k in case.get("selection_avoid_only") or [] if k.lower() in blob_l]
    needed = case.get("needed_in_context_any") or []
    needed_hit = [k for k in needed if k.lower() in blob_l]
    clarify_ok = bool(case.get("clarify_ok")) and transition == "CLARIFY"
    match = bool(hits) or clarify_ok
    if needed and not needed_hit and not clarify_ok:
        match = False
    # If avoid terms dominate and intended hits are absent
    if avoid and not hits and not clarify_ok:
        match = False
    return {
        "selection_match": match,
        "selection_hits": hits,
        "selection_avoid_hits": avoid,
        "needed_hits": needed_hit,
        "clarify_counted_ok": clarify_ok,
    }


def score_answer(case: dict, answer: str, clarify: bool) -> dict:
    if clarify and case.get("clarify_ok"):
        return {
            "answer_correct": True,
            "answer_note": "CLARIFY legitimate for this ambiguous target",
            "ok_hits": [],
            "bad_hits": [],
        }
    if clarify and not case.get("clarify_ok"):
        # fail-closed: not automatically wrong
        return {
            "answer_correct": None,
            "answer_note": "CLARIFY; not counted automatically wrong",
            "ok_hits": [],
            "bad_hits": [],
        }
    ok = contains_any(answer, case.get("answer_ok_any") or [])
    bad = contains_any(answer, case.get("answer_bad_any") or [])
    correct = bool(ok) and not bad
    note = "ok" if correct else ("wrong_or_insufficient" if not ok else "contains_forbidden")
    return {
        "answer_correct": correct,
        "answer_note": note,
        "ok_hits": [k for k in (case.get("answer_ok_any") or []) if k.lower() in answer.lower()],
        "bad_hits": [k for k in (case.get("answer_bad_any") or []) if k.lower() in answer.lower()],
    }


def failure_mode(case: dict, sel: dict, ans: dict, clarify: bool, context: str) -> str:
    if clarify and case.get("clarify_ok"):
        return "legitimate_ambiguity_or_clarify"
    if clarify:
        return "legitimate_ambiguity_or_clarify"
    if ans.get("bad_hits"):
        return "wrong_context"
    if not sel.get("selection_match"):
        return "wrong_context"
    needed = case.get("needed_in_context_any") or []
    if needed and not sel.get("needed_hits"):
        return "insufficient_context"
    if ans.get("answer_correct") is False:
        if token_count(context) < 40:
            return "insufficient_context"
        return "answer_model_error_given_good_context"
    return "none"


def run_case(case: dict, dialogues: dict, llm: ProposeOnlyLLM) -> dict:
    d = dialogues[case["dialogue_id"]]
    history = transcript_before_target(d, case["target_turn_id"])
    target = target_user(d, case["target_turn_id"])
    full = format_turns(history)
    rec = recency_context(history)
    jac = jaccard_context(history, target)

    print(f"\n=== {case['id']} target={case['target_turn_id']} {case['difficulty']} ===", flush=True)
    print(f"  CF replay ({len([h for h in history if h['speaker']=='USER'])} user turns)...", flush=True)
    cf = replay_cf(history, target, llm)
    cf_clarify = cf["transition"] == "CLARIFY"
    cf_context = cf["clarify_question"] if cf_clarify else (cf["compiled"] or "")

    print("  LLM-only select...", flush=True)
    llm_ctx = llm_select_context(history, target)

    conditions = {
        "full_history": full,
        "recency": rec,
        "jaccard": jac,
        "llm_only": llm_ctx,
        "contextflow": cf_context,
    }
    rows = {}
    for name, ctx in conditions.items():
        print(f"  answer {name}...", flush=True)
        t0 = time.perf_counter()
        if name == "contextflow" and cf_clarify:
            answer = cf["clarify_question"] or ""
        else:
            answer = generate_answer(ctx, target)
        elapsed = round(time.perf_counter() - t0, 2)
        blob = ctx if name != "contextflow" else (cf.get("selected_blob") or ctx)
        sel = score_selection(
            case, blob,
            transition=cf["transition"] if name == "contextflow" else None,
        )
        ans = score_answer(
            case, answer,
            clarify=(name == "contextflow" and cf_clarify),
        )
        rows[name] = {
            "context": ctx,
            "context_chars": len(ctx),
            "context_tokens_heuristic": token_count(ctx),
            "answer": answer,
            "latency_s": elapsed,
            **sel,
            **ans,
            "failure_mode": failure_mode(case, sel, ans, name == "contextflow" and cf_clarify, ctx),
        }

    return {
        "id": case["id"],
        "headline": case["headline"],
        "difficulty": case["difficulty"],
        "phenomenon": case["phenomenon"],
        "genuine_return": case["genuine_return"],
        "intended_workstream": case["intended_workstream"],
        "intended_note": case["intended_note"],
        "target": target,
        "n_history_turns": len(history),
        "contextflow_routing": {
            "transition": cf["transition"],
            "task_id": cf["task_id"],
            "predicted_task_id": cf["predicted_task_id"],
            "predicted_referent_id": cf["predicted_referent_id"],
            "clarify_question": cf["clarify_question"],
            "proposal": cf["proposal"],
            "top_raw": cf["top_raw"],
            "raw_margin": cf["raw_margin"],
            "evidence": cf["evidence"],
            "replay_log": cf["replay_log"],
            "cards_before_target": cf["cards_before_target"],
            "answer_tokens": cf["answer_tokens"],
            "decision_tokens": cf["decision_tokens"],
        },
        "conditions": rows,
    }


def main() -> int:
    os.environ.setdefault("OLLAMA_MODEL", ANSWER_MODEL)
    if not DATA.is_file():
        print(f"missing {DATA}")
        return 1
    print("warmup ollama llama3.1:8b...", flush=True)
    try:
        gen = json.dumps({
            "model": ANSWER_MODEL, "prompt": "OK", "stream": False,
            "options": {"temperature": 0.0},
        }).encode("utf-8")
        req = urllib.request.Request(
            os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/generate",
            data=gen, headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=300).read()
        ollama_chat(ANSWER_MODEL, "You reply OK.", "Reply with OK only.")
    except Exception as exc:
        print(f"ollama failed: {exc}")
        return 1
    dialogues = load_dialogues()
    inner = OllamaLLM(model=ANSWER_MODEL, timeout_s=300.0)
    llm = ProposeOnlyLLM(inner)
    out_json = OUT_DIR / "run.json"
    payload = {
        "answer_model": ANSWER_MODEL,
        "recency_k": RECENCY_K,
        "jaccard_m": JACCARD_M,
        "settings": {"TAU": SETTINGS.TAU, "DELTA": SETTINGS.DELTA, "HYST": SETTINGS.HYST},
        "note": (
            "DST unused as memory. Future wizard turns unused. "
            "System utterances attached to the active CF card via eval-only apply_update. "
            "Production gate/scorer/compiler not modified."
        ),
        "cases": [],
    }
    done = set()
    if out_json.is_file():
        try:
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            payload.setdefault("cases", [])
            done = {c["id"] for c in payload["cases"]}
            print(f"resume: already have {sorted(done)}", flush=True)
        except json.JSONDecodeError:
            print("resume: run.json unreadable, starting fresh", flush=True)
    for case in CASES:
        if case["id"] in done:
            print(f"skip {case['id']} (checkpoint)", flush=True)
            continue
        row = run_case(case, dialogues, llm)
        payload["cases"].append(row)
        out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"checkpoint {case['id']} -> {out_json}", flush=True)
    print(f"\nwrote {out_json}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
