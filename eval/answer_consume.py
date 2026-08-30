"""Tiny local answer-model consume test. Ollama generate only. No Vertex.

3 probes × FULL / RECENT / ContextFlow. Routing stays MockLLM (frozen).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.config import SETTINGS
from app.context.compiler import ContextCompiler
from app.engine import Engine
from app.llm.mock import MockLLM
from app.memory.extractor import MockMemoryExtractor
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.turn_pipeline import run_turn
from eval.consented_case.contexts import contextflow_answer_prompt, full_history_prompt, recent_prompt
from eval.memory_lifecycle.fixture import EXTRACT_SCRIPTS, LLM_SCRIPTS, PRODUCT_USER_TURNS
from eval.memory_lifecycle.run import make_registry

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "out" / "answer_consume.json"

PROBES = (7, 8, 9)  # return B (black) / return A / correct B navy


def ollama_available() -> bool:
    import urllib.request
    try:
        from app.llm.ollama import OllamaLLM
        url = OllamaLLM().base_url + "/api/tags"
        urllib.request.urlopen(url, timeout=2.0).read()
        return True
    except Exception:
        return False


def replay():
    cid = "answer-consume"
    reg = make_registry()
    store = InMemoryMemoryStore(conversation_id=cid)
    writer = MemoryWriter(store, reg)
    eng = Engine(MockLLM(LLM_SCRIPTS), reg, SETTINGS, memory_store=store)
    ext = MockMemoryExtractor(EXTRACT_SCRIPTS)
    snaps = {}
    for turn, msg, _ in PRODUCT_USER_TURNS:
        snaps[turn] = run_turn(
            eng, writer, ext, conversation_id=cid, message=msg, turn=turn,
        )
    return snaps


def history_before(engine_turn: int) -> list[dict]:
    hist = []
    i = 0
    for et, msg, _ in PRODUCT_USER_TURNS:
        if et >= engine_turn:
            break
        hist.append({"i": i, "role": "user", "text": msg})
        i += 1
        hist.append({"i": i, "role": "assistant", "text": "[stub]"})
        i += 1
    return hist


def run() -> dict:
    if not ollama_available():
        payload = {
            "status": "skipped",
            "reason": "ollama_unreachable",
            "note": "Local daemon required. Not a Vertex substitute failure.",
        }
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    from app.llm.ollama import OllamaLLM
    llm = OllamaLLM()
    snaps = replay()
    compiler = ContextCompiler()
    rows = []
    for et in PROBES:
        msg = next(m for t, m, _ in PRODUCT_USER_TURNS if t == et)
        hist = history_before(et)
        pkg = snaps[et].turn.package
        rendered = compiler.render(pkg) if pkg else ""
        prompts = {
            "full": full_history_prompt(hist, msg),
            "recent": recent_prompt(hist, msg, 8),
            "contextflow": contextflow_answer_prompt(rendered, msg),
        }
        answers = {k: llm.generate(v) for k, v in prompts.items()}
        needed = {
            7: ["black", "formal"],
            8: ["401"],
            9: ["navy", "formal"],
        }[et]
        used = {}
        for name, ans in answers.items():
            blob = (ans or "").lower()
            used[name] = {n: n.lower() in blob for n in needed}
        winner = []
        if all(used["full"].values()) and not all(used["contextflow"].values()):
            winner.append("FULL")
        if all(used["contextflow"].values()) and not all(used["full"].values()):
            winner.append("CF")
        if all(used["full"].values()) and all(used["contextflow"].values()):
            winner.append("both")
        rows.append({
            "engine_turn": et,
            "message": msg,
            "task_id": snaps[et].turn.task_id,
            "needed": needed,
            "used_in_answer": used,
            "winner": winner or ["none_clear"],
            "answers": answers,
            "cf_package": rendered,
        })
    payload = {
        "status": "ran",
        "provider": "ollama",
        "model": llm.model,
        "n_generate": 9,
        "probes": rows,
        "note": "String overlap in answers is a weak signal. FULL winning is recorded.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def main() -> int:
    payload = run()
    print(json.dumps({"status": payload.get("status"), "out": str(OUT),
                      "n": len(payload.get("probes") or [])}, indent=2))
    return 0 if payload.get("status") in ("ran", "skipped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
