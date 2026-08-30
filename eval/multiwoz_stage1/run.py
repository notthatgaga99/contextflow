"""Stage-1 routing only. Mock/lexical proposal. No answer model. No Vertex."""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.config import SETTINGS
from app.engine import Engine
from app.llm.mock import MockLLM
from app.llm.tokens import count as token_count
from app.memory.registry import InMemoryRegistry
from app.context.compiler import ContextCompiler

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "multiwoz" / "dialogues_001.json"
OUT = Path(__file__).resolve().parent / "stage1.json"

# Hand-reviewed after utterance inspect. Not DST-manufactured.
# class uses the 8-way scheme from the research brief.
STAGE1_CASES = [
    {
        "id": "PMUL0079",
        "dialogue_id": "PMUL0079.json",
        "target_turn_id": 8,
        "class": "interruption",
        "also": ["genuine_return"],
        "intended": "hotel",
        "note": "Before we do that → guesthouse name/parking. Restaurant already started.",
    },
    {
        "id": "MUL0810",
        "dialogue_id": "MUL0810.json",
        "target_turn_id": 12,
        "class": "genuine_return",
        "also": ["explicit_named"],
        "intended": "attraction",
        "note": "Forgot to ask museum postcode after restaurant.",
    },
    {
        "id": "MUL2423",
        "dialogue_id": "MUL2423.json",
        "target_turn_id": 12,
        "class": "ambiguous",
        "also": ["genuine_return", "deictic"],
        "intended": "attraction",
        "note": "Taxi started; which theatre. None named yet. CLARIFY legal.",
        "clarify_ok": True,
    },
    {
        "id": "PMUL4186",
        "dialogue_id": "PMUL4186.json",
        "target_turn_id": 8,
        "class": "correction",
        "also": ["genuine_return"],
        "intended": "hotel",
        "note": "Wizard answered Nando's; user re-asks Belfry. Named in target.",
    },
    {
        "id": "MUL2053",
        "dialogue_id": "MUL2053.json",
        "target_turn_id": 14,
        "class": "copy_from_prior",
        "also": [],
        "intended": "hotel",  # day constraint lives on hotel; current ask is train
        "intended_note": "Not a return-to-hotel Q&A. Need Tuesday from hotel stay.",
        "note": "On the same day as the hotel stay.",
    },
    {
        "id": "PMUL2746",
        "dialogue_id": "PMUL2746.json",
        "target_turn_id": 10,
        "class": "copy_from_prior",
        "also": [],
        "intended": "hotel",
        "note": "The same as the hotel please (area). Attraction is current ask.",
    },
    {
        "id": "MUL0088",
        "dialogue_id": "MUL0088.json",
        "target_turn_id": 10,
        "class": "deictic",
        "also": ["interruption"],
        "intended": "hotel",
        "note": "Does it have internet? after restaurant named and lodge offered.",
    },
]

DOMAIN_WORDS = {
    "hotel": ("hotel", "guesthouse", "guest house", "lodge", "belfry", "hamilton"),
    "restaurant": ("restaurant", "food", "nandos", "nando", "pizza", "italian"),
    "attraction": ("attraction", "museum", "theatre", "theater", "college"),
    "train": ("train", "peterborough"),
    "taxi": ("taxi",),
}


class LexicalCardProposer(MockLLM):
    """Eval-only proposer: overlap with CF cards, else NEW. Production MockLLM unchanged."""

    def propose(self, prompt: str, schema: dict) -> dict:
        msg = self._extract_message(prompt).lower()
        cards = re.findall(
            r"\[(T\d+)\] goal: (.*?); open_loops: (.*?); last_active_turn:",
            prompt,
            re.S,
        )
        if not cards:
            return {
                "task_id": None, "is_new_task": True, "confidence": 0.9,
                "referent": None, "rationale": "eval-lexical-new-empty",
            }
        scored = []
        mw = set(re.findall(r"[a-z0-9]+", msg))
        for tid, goal, loops in cards:
            blob = f"{goal} {loops}".lower()
            tw = set(re.findall(r"[a-z0-9]+", blob))
            hit = len(mw & tw)
            scored.append((hit, tid))
        scored.sort(reverse=True)
        best, tid = scored[0]
        runner = scored[1][0] if len(scored) > 1 else 0
        if best <= 0:
            return {
                "task_id": None, "is_new_task": True, "confidence": 0.85,
                "referent": None, "rationale": "eval-lexical-new",
            }
        if best == runner:
            return {
                "task_id": None, "is_new_task": False, "confidence": 0.2,
                "referent": None, "rationale": "eval-lexical-tie",
            }
        return {
            "task_id": tid, "is_new_task": False, "confidence": min(0.9, 0.4 + 0.05 * best),
            "referent": None, "rationale": "eval-lexical-match",
        }

    def generate(self, prompt: str) -> str:
        return ""


def load_map() -> dict:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    return {d["dialogue_id"]: d for d in data}


def history_and_target(d: dict, target_id: int) -> tuple[list[dict], str]:
    hist = []
    target = ""
    for t in d["turns"]:
        tid = int(t["turn_id"])
        row = {
            "turn_id": tid,
            "speaker": t["speaker"],
            "text": t["utterance"].replace("\n", " ").strip(),
        }
        if tid < target_id:
            hist.append(row)
        elif tid == target_id:
            target = row["text"]
            break
    return hist, target


def ingest_system(reg: InMemoryRegistry, text: str) -> None:
    active = reg.active()
    if active is None:
        return
    snippet = f"SYSTEM: {text}"
    if snippet not in active.anchor.open_loops:
        reg.apply_update(active.id, {"open_loops": [snippet]})
        for w in re.findall(r"[a-zA-Z]{4,}", text)[:6]:
            lw = w.lower()
            if lw not in active.retrieval_cues:
                active.retrieval_cues.append(lw)


def domain_of(blob: str) -> str | None:
    low = blob.lower()
    hits = []
    for dom, kws in DOMAIN_WORDS.items():
        if any(k in low for k in kws):
            hits.append(dom)
    if len(hits) == 1:
        return hits[0]
    if "hotel" in hits and "restaurant" in hits:
        return None
    return hits[0] if hits else None


def replay(hist: list[dict], target: str) -> dict:
    llm = LexicalCardProposer()
    reg = InMemoryRegistry()
    eng = Engine(llm, reg, SETTINGS, mode="split")
    log = []
    for t in hist:
        if t["speaker"] == "USER":
            res = eng.handle_turn(t["text"], t["turn_id"] + 1)
            log.append({
                "turn_id": t["turn_id"],
                "transition": res.transition.value,
                "task_id": res.task_id,
            })
        else:
            ingest_system(reg, t["text"])
    cards_before = [
        {
            "id": t.id, "title": t.title, "status": t.status,
            "goal": t.anchor.goal,
            "n_loops": len(t.anchor.open_loops),
            "mention_turn": t.mention_turn,
            "last_active_turn": t.last_active_turn,
        }
        for t in reg.open_tasks()
    ]
    n_open = len(reg.open_tasks())
    prior_last = {c["id"]: c["last_active_turn"] for c in cards_before}
    hist_text = "\n".join(f"{x['speaker']}: {x['text']}" for x in hist)
    target_turn = (hist[-1]["turn_id"] + 2) if hist else 1
    res = eng.handle_turn(target, target_turn)
    compiler = ContextCompiler()
    task = reg.get(res.task_id) if res.task_id else None
    compact = None
    full_task = None
    if task is not None:
        compact = compiler.build(
            task, "split",
            selected_referent_id=res.predicted_referent_id,
            selected_open_loop=None,
            message=target,
            open_tasks=reg.open_tasks(),
        )
        full_task = compiler.build(
            task, "full",
            selected_referent_id=res.predicted_referent_id,
            selected_open_loop=None,
            message=target,
            open_tasks=reg.open_tasks(),
        )
    blob = ""
    if task:
        blob = f"{task.title} {task.anchor.goal} {' '.join(task.anchor.open_loops)}"
    pred_dom = domain_of(blob)
    last_active_before = prior_last.get(res.task_id) if res.task_id else None
    return_distance = None
    if last_active_before is not None:
        return_distance = target_turn - last_active_before
    other_open = n_open
    return {
        "transition": res.transition.value,
        "task_id": res.task_id,
        "predicted_task_id": res.predicted_task_id,
        "predicted_referent_id": res.predicted_referent_id,
        "clarify": res.clarify_question,
        "top_raw": res.decision.top_raw,
        "raw_margin": res.decision.raw_margin,
        "candidate_count": len(res.decision.candidates),
        "open_task_count": res.decision.open_task_count,
        "predicted_domain": pred_dom,
        "selected_blob": blob[:800],
        "return_distance": return_distance,
        "concurrent_workstreams": other_open,
        "n_history_turns": len(hist),
        "full_history_tokens": token_count(hist_text),
        "answer_tokens_compact": compact.answer_tokens if compact else 0,
        "answer_tokens_full_task": full_task.answer_tokens if full_task else 0,
        "decision_tokens": compact.decision_tokens if compact else 0,
        "compiled_compact": compiler.render(compact) if compact else "",
        "compiled_full_task": compiler.render(full_task) if full_task else "",
        "replay_log": log,
        "cards_before_target": cards_before,
        "evidence": dict(res.resolution_evidence or {}),
        "last_active_turn": last_active_before,
    }


def selection_match(case: dict, row: dict) -> bool:
    if case.get("clarify_ok") and row["transition"] == "CLARIFY":
        return True
    intended = case["intended"]
    if row["predicted_domain"] == intended:
        return True
    blob = (row.get("selected_blob") or "").lower()
    if any(k in blob for k in DOMAIN_WORDS.get(intended, ())):
        return True
    return False


def main() -> None:
    dialogues = load_map()
    rows = []
    for case in STAGE1_CASES:
        d = dialogues[case["dialogue_id"]]
        hist, target = history_and_target(d, case["target_turn_id"])
        out = replay(hist, target)
        match = selection_match(case, out)
        fail = "none"
        if out["transition"] == "CLARIFY":
            fail = "legitimate_ambiguity_or_clarify" if case.get("clarify_ok") else "clarify_not_auto_wrong"
        elif not match:
            fail = "wrong_context"
        print(
            f"{case['id']} t{case['target_turn_id']} {case['class']} "
            f"{out['transition']} task={out['task_id']} dom={out['predicted_domain']} "
            f"match={match} open={out['concurrent_workstreams']} "
            f"hist_tok={out['full_history_tokens']} compact_tok={out['answer_tokens_compact']}"
        )
        rows.append({
            **case,
            "target": target,
            "selection_match": match,
            "failure": fail,
            **out,
        })
    payload = {
        "settings": {"TAU": SETTINGS.TAU, "DELTA": SETTINGS.DELTA, "HYST": SETTINGS.HYST},
        "proposer": "eval LexicalCardProposer (not production Mock default-NEW)",
        "n_cases": len(rows),
        "n_selection_match": sum(1 for r in rows if r["selection_match"]),
        "cases": rows,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
