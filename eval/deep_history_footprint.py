"""Exercise DEEP warm-up against hosted ContextFlow; report per-thread footprint."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://contextflow-cjraqyv4hq-el.a.run.app"
OUT = Path(__file__).resolve().parents[1] / "eval" / "out" / "deep_history_footprint.json"

# Same beats as app/api/static/index.html DEEP (keep in sync).
DEEP = [
    "We're on branch feat/submission-polish. Cloud Run service contextflow is public. Do NOT redesign gate/referent/scorer. Help me debug why judges hit {\"detail\":\"Not Found\"} on the root URL.",
    "Root path / has no route — only /docs /health /turn. Confirm that's expected for FastAPI, then propose the smallest fix so / shows a clean UI without touching routing freeze files.",
    "Azure DevOps-style check: pytest is green locally (312 passed) but the pipeline image build failed after COPY . . — no .dockerignore. List what must be excluded so we don't ship .env or eval/out.",
    "Hypothesis: POST /turn 401 after refresh is because middleware rejects expired access tokens and never accepts the rotated refresh cookie. Walk the request path and tell me what to log first.",
    "We log correlation_id but not token_kind. Assume refresh hits /turn with Authorization Bearer <access>. If access is expired, should we return 401 with machine-readable code refresh_required?",
    "Correction: it's NOT the refresh cookie. Staging shows identity token missing on unauthenticated clients — Cloud Run IAM returns 403 HTML, not our FastAPI 401. Update the diagnosis.",
    "We have contextflow (public demo) and contextflow-durable (IAM invoker only). Judges must use the public UI URL. Write a one-paragraph hackathon form note.",
    "Before redeploy: GET / UI, Vertex extract+answer only, CF_LLM_EXTRACT=1, CF_SEED_ABCD=0, max instances 2. Confirm env flags and rollback.",
    "Cloud Logging query for turn_decision on service contextflow — which fields prove extract_ok and transition without logging raw user text?",
    "Give the exact git diff command to prove gate.py referent.py scorer.py config.py writer.py unchanged vs freeze commit 8cc5539.",
    "origin/main is still scaffold. Release is on feat/submission-polish. What GitHub URL should the form use until we update main?",
    "Quick switch — ignore engineering. Draft a warm 90-second hosting script for Friday office townhall. Thank volunteers; one ContextFlow shout-out.",
    "Shorten to 45 seconds. Remove jargon. Keep: leave a thought without losing it.",
    "Different thread: Lisbon trip planning. Hotel needs parking near the center. Mid-range budget, 4 nights.",
    "Prefer walkable neighborhoods. Add a note that airport traffic was mentioned in the deck — don't let that contaminate the hotel choice.",
    "Another thread: best friend's haldi this weekend. Festive but comfortable. Assuming black is fine for evening.",
    "Actually navy, not black — formal evening. Keep black as old assumption for audit. What should CURRENT vs HISTORY look like?",
    "Also no heavy embroidery — need to dance. Prefer breathable fabrics.",
]

REVIVE = [
    ("lisbon", "What about Alfama for my Lisbon stay — walkable, still okay with parking nearby?"),
    ("eng", "Okay, back to the Cloud Run / FastAPI judge access issue — continue from the IAM vs FastAPI diagnosis, don't restart."),
    ("navy", "Maybe the navy one?"),
]


def http_json(method: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        BASE.rstrip("/") + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} -> {e.code}: {raw[:500]}") from e


def main() -> None:
    cid = f"deep-fp-{int(time.time())}"
    routes = []
    turn = 1
    print(f"BASE={BASE}\ncid={cid}\nhealth={http_json('GET', '/health')}")
    for i, msg in enumerate(DEEP, 1):
        print(f"\n--- DEEP {i}/{len(DEEP)} turn={turn} ---", flush=True)
        out = http_json("POST", "/turn", {"conversation_id": cid, "message": msg, "turn": turn})
        turn += 1
        routes.append({
            "phase": "deep",
            "i": i,
            "transition": out.get("transition"),
            "task_id": out.get("task_id"),
            "title": out.get("workstream_title"),
            "extract_ok": out.get("extract_ok"),
        })
        print(
            f"  {out.get('transition')} · {out.get('workstream_title')} · extract_ok={out.get('extract_ok')}",
            flush=True,
        )
        time.sleep(0.4)

    for key, msg in REVIVE:
        print(f"\n--- REVIVE {key} turn={turn} ---", flush=True)
        out = http_json("POST", "/turn", {"conversation_id": cid, "message": msg, "turn": turn})
        turn += 1
        routes.append({
            "phase": "revive",
            "key": key,
            "transition": out.get("transition"),
            "task_id": out.get("task_id"),
            "title": out.get("workstream_title"),
            "extract_ok": out.get("extract_ok"),
            "answer_preview": (out.get("clarify_question") or out.get("answer") or "")[:180],
        })
        print(
            f"  {out.get('transition')} · {out.get('workstream_title')}",
            flush=True,
        )
        time.sleep(0.4)

    mem = http_json("GET", f"/conversations/{cid}/memory")
    tasks = http_json("GET", f"/conversations/{cid}/tasks").get("tasks") or []
    footprints = []
    for t in tasks:
        wc = http_json(
            "GET",
            f"/conversations/{cid}/working-context?task_id={urllib.parse.quote(t['id'])}",
        )
        inc = wc.get("included") or {}
        lines = []
        for k in ("decisions", "constraints", "facts", "entities"):
            lines.extend(inc.get(k) or [])
        ws = next((w for w in (mem.get("workstreams") or []) if w["id"] == t["id"]), {})
        hist = ws.get("history") or []
        footprints.append({
            "id": t["id"],
            "title": t.get("title"),
            "status": t.get("status"),
            "current_lines": lines,
            "current_count": len(lines),
            "current_chars": sum(len(str(x)) for x in lines),
            "history_count": len(hist),
            "history_texts": [h.get("text") for h in hist],
            "asserted_decisions": ws.get("decisions") or [],
            "asserted_constraints": ws.get("constraints") or [],
            "asserted_facts": ws.get("facts") or [],
            "excluded_workstreams": wc.get("excluded_workstreams") or [],
        })
        print(
            f"THREAD {t.get('title')}: current={len(lines)} lines / "
            f"{sum(len(str(x)) for x in lines)} chars · history={len(hist)} · "
            f"excluded={len(wc.get('excluded_workstreams') or [])}",
            flush=True,
        )

    report = {
        "base": BASE,
        "conversation_id": cid,
        "deep_turns": len(DEEP),
        "revive_turns": len(REVIVE),
        "routes": routes,
        "footprints": footprints,
        "note": "Working-context chars = projected CURRENT for that thread only; not full chat dump.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
