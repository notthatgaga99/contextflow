"""Density extract slice on Vertex Flash-Lite (same turns as Ollama density harness).

CONTROLLED — not natural chat. No routing. Writer validates. ≤12 extract calls.
Uses structured propose() via GeminiClient (not free-form generate JSON).

  set GOOGLE_APPLICATION_CREDENTIALS=...
  set GCP_PROJECT=contextflow-gagan-20261019
  set CF_USE_VERTEX=1
  python -m eval.ten_workstream.extract_density_vertex
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from app.context.working_set import WorkingContextBuilder
from app.memory.extractor import ExtractRequest, LlmMemoryExtractor
from app.memory.store import InMemoryMemoryStore
from app.memory.writer import MemoryWriter
from app.models.memory import MemoryPatch
from eval.ten_workstream.extract_density_ollama import SUBSET, _classify, _need_hit
from eval.ten_workstream.load import load_fixture
from eval.ten_workstream.run import make_registry

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "eval" / "ten_workstream" / "fixture_10x20.json"
OUT = ROOT / "eval" / "out" / "extract_density_vertex.json"
OLLAMA_OUT = ROOT / "eval" / "out" / "extract_density_ollama.json"
RESULTS_MD = ROOT / "docs" / "EXTRACT_DENSITY_VERTEX.md"

MAX_CALLS = 12
PRICE_IN_PER_M = 0.10
PRICE_OUT_PER_M = 0.40
SAFETY_ENVELOPE_USD = 0.05


def _brief_patch(p: MemoryPatch) -> dict:
    return {
        "kind": p.kind, "text": p.text, "workstream_id": p.workstream_id,
        "slot": p.slot, "uncertain": p.uncertain, "action": p.action,
    }


class CountingVertexExtract:
    """Count propose/generate toward hard cap. Duck-types as structured extract LLM."""

    def __init__(self, inner, *, max_calls: int = MAX_CALLS):
        self.inner = inner
        self.max_calls = max_calls
        self.calls = 0
        self.prompt_tokens = 0
        self.candidates_tokens = 0
        self.LITE_MODEL = inner.LITE_MODEL
        self.GEN_MODEL = inner.GEN_MODEL
        self._types = inner._types_mod
        self._client = inner._client

    def _bump(self, r) -> None:
        self.calls += 1
        if self.calls > self.max_calls:
            raise RuntimeError(f"density_vertex_call_cap_{self.max_calls}")
        meta = getattr(r, "usage_metadata", None)
        if meta is not None:
            self.prompt_tokens += int(getattr(meta, "prompt_token_count", 0) or 0)
            self.candidates_tokens += int(getattr(meta, "candidates_token_count", 0) or 0)

    def propose(self, prompt: str, schema: dict) -> dict:
        r = self._client.models.generate_content(
            model=self.LITE_MODEL,
            contents=prompt,
            config=self._types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        self._bump(r)
        return json.loads(r.text)

    def generate(self, prompt: str) -> str:
        r = self._client.models.generate_content(
            model=self.GEN_MODEL,
            contents=prompt,
            config=self._types.GenerateContentConfig(temperature=0.2),
        )
        self._bump(r)
        return r.text

    def cost_usd(self) -> float:
        return (
            self.prompt_tokens * PRICE_IN_PER_M / 1_000_000
            + self.candidates_tokens * PRICE_OUT_PER_M / 1_000_000
        )


def run() -> dict:
    label = "CONTROLLED_10x20_DENSITY_EXTRACT_VERTEX"
    if os.getenv("CF_USE_VERTEX") != "1" and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        payload = {"status": "skipped", "reason": "set_CF_USE_VERTEX_and_GCP_creds", "label": label}
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    os.environ.setdefault("CF_USE_VERTEX", "1")
    os.environ.setdefault("GCP_PROJECT", os.getenv("GCP_PROJECT") or "contextflow-gagan-20261019")
    os.environ.setdefault("GCP_REGION", "us-central1")
    os.environ.setdefault("CF_VERTEX_LOCATION", "us-central1")
    os.environ.setdefault("CF_LITE_MODEL", "gemini-2.5-flash-lite")
    os.environ.setdefault("CF_GEN_MODEL", "gemini-2.5-flash-lite")
    os.environ.setdefault("CF_EMBED_LOCAL", "1")

    from app.llm.gemini import GeminiClient
    llm = CountingVertexExtract(GeminiClient(use_vertex=True))

    fx = load_fixture(FIXTURE)
    turn_by = {int(t["turn"]): t for t in fx["turns"]}
    reg = make_registry(fx)
    store = InMemoryMemoryStore(conversation_id="ten-extract-density-vertex")
    writer = MemoryWriter(store, reg)
    ext = LlmMemoryExtractor(llm)

    rows = []
    t0 = time.perf_counter()
    for spec in sorted(SUBSET, key=lambda s: s["turn"]):
        tspec = turn_by[spec["turn"]]
        msg = tspec["message"]
        open_ws = reg.open_tasks() if spec["mode"] == "anchored" else []
        req = ExtractRequest(
            message=msg,
            source_turn=spec["turn"],
            conversation_id="ten-extract-density-vertex",
            open_workstreams=open_ws,
            asserted_items=store.asserted(),
            focus_workstream_id=spec.get("expect_ws"),
        )
        before = {i.id for i in store.all()}
        extracted = ext.extract(req)
        patches = list(extracted.patches or [])
        proposed = writer.propose(patches)
        result = writer.validate(proposed)
        persisted = []
        commit_errors: list[str] = []
        if result.ok and proposed:
            committed = writer.commit(proposed, turn=spec["turn"])
            if not committed.ok:
                commit_errors = list(committed.errors or [])
                result = committed
            persisted = [
                i for i in store.all()
                if i.id not in before and i.status == "asserted"
            ]

        expect_ws = spec.get("expect_ws")
        ws_ids = {p.workstream_id for p in proposed if p.workstream_id}
        wrong_ws = bool(
            expect_ws and proposed and expect_ws not in ws_ids
            and not spec.get("expect_uncertain_or_empty")
        )
        blob = " ".join(p.text for p in proposed)
        need = list(spec.get("need_tokens") or [])
        need_ok = (not need) or _need_hit(blob, need)
        expect_slot = spec.get("expect_slot")
        slot_ok = None
        if expect_slot and not spec.get("expect_uncertain_or_empty"):
            slot_ok = any(p.slot == expect_slot for p in proposed) or any(
                i.slot == expect_slot for i in store.asserted(expect_ws or "")
            )
        recon = "n/a"
        useful = False
        partial = False
        if expect_ws and not spec.get("expect_uncertain_or_empty"):
            proj = WorkingContextBuilder().project(
                reg.get(expect_ws), None, store, reg.open_tasks(),
            )
            pkg = " ".join(proj.decisions + proj.constraints + proj.facts + proj.entities)
            if need and _need_hit(pkg, need):
                recon = "ok"
                useful = not wrong_ws and bool(persisted or need_ok)
                # useful if reconstructed even via prior persist
                if _need_hit(pkg, need) and not wrong_ws:
                    useful = True
                    recon = "ok"
            elif persisted:
                recon = "missing_required"
                partial = not wrong_ws
            else:
                recon = "missing_required"

        fail_closed_ok = False
        if spec.get("expect_uncertain_or_empty"):
            fail_closed_ok = (
                len(proposed) == 0
                or all(p.uncertain for p in proposed)
                or any("recall" in n or "abstain" in n for n in (extracted.notes or []))
            )

        row = {
            "id": spec["id"],
            "turn": spec["turn"],
            "ws_intended": tspec["ws"],
            "category": spec["category"],
            "message": msg,
            "expect_slot": expect_slot,
            "slot_ok": slot_ok,
            "proposed": [_brief_patch(p) for p in proposed],
            "persisted": len(persisted),
            "writer_ok": result.ok,
            "writer_errors": list(result.errors or []) or commit_errors,
            "wrong_workstream": wrong_ws,
            "need_ok": need_ok,
            "reconstruction": recon,
            "useful": useful,
            "partial": partial,
            "expect_uncertain_or_empty": bool(spec.get("expect_uncertain_or_empty")),
            "fail_closed_ok": fail_closed_ok,
            "notes": list(extracted.notes or [])[:8],
        }
        row["class"] = _classify(row)
        rows.append(row)

    elapsed = round(time.perf_counter() - t0, 3)
    taxonomy: dict[str, int] = {}
    for r in rows:
        taxonomy[r["class"]] = taxonomy.get(r["class"], 0) + 1

    revive_ready = {}
    for wid, tokens in (
        ("A", ["5", "api.internal"]),
        ("B", ["debian", "4"]),
        ("E", ["navy", "peplum"]),
    ):
        proj = WorkingContextBuilder().project(
            reg.get(wid), None, store, reg.open_tasks(),
        )
        pkg = " ".join(proj.decisions + proj.constraints + proj.facts + proj.entities)
        revive_ready[wid] = {
            "present": [t for t in tokens if t.lower() in pkg.lower()],
            "missing": [t for t in tokens if t.lower() not in pkg.lower()],
            "pkg_chars": len(pkg),
        }

    cost = llm.cost_usd()
    ollama_cmp = None
    if OLLAMA_OUT.exists():
        prev = json.loads(OLLAMA_OUT.read_text(encoding="utf-8"))
        ollama_cmp = {
            "useful": prev.get("useful"),
            "taxonomy": prev.get("taxonomy"),
            "model": prev.get("model"),
        }

    payload = {
        "status": "ran",
        "label": label,
        "fixture": "eval/ten_workstream/fixture_10x20.json",
        "model": llm.LITE_MODEL,
        "project": os.environ.get("GCP_PROJECT"),
        "region": os.environ.get("CF_VERTEX_LOCATION") or os.environ.get("GCP_REGION"),
        "n_generate": llm.calls,
        "prompt_tokens": llm.prompt_tokens,
        "candidates_tokens": llm.candidates_tokens,
        "actual_usd_est": round(cost, 6),
        "within_envelope": cost <= SAFETY_ENVELOPE_USD,
        "elapsed_s": elapsed,
        "taxonomy": taxonomy,
        "useful": taxonomy.get("USEFUL", 0),
        "abstain_ok": taxonomy.get("ABSTAIN_OK", 0),
        "wrong_ws": taxonomy.get("WRONG_WS", 0),
        "revive_ready_after_slice": revive_ready,
        "ollama_compare": ollama_cmp,
        "rows": rows,
        "note": (
            "Structured Vertex extract on 10×20 density cues. "
            "Not full 200-turn extract. Gate unused."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _write_md(payload)
    return payload


def _write_md(payload: dict) -> None:
    if payload.get("status") != "ran":
        RESULTS_MD.write_text(
            f"# Extract density (Vertex)\n\nSkipped: {payload.get('reason')}\n",
            encoding="utf-8",
        )
        return
    tax = payload.get("taxonomy") or {}
    oc = payload.get("ollama_compare") or {}
    lines = [
        "# Extract density under 10×20 cues (Vertex Flash-Lite)",
        "",
        "**CONTROLLED density-extract slice** — not natural chat, not production accuracy.",
        "No routing. Writer validates. Structured `propose()` + schema.",
        "",
        f"**Model:** `{payload.get('model')}` @ `{payload.get('project')}` / "
        f"`{payload.get('region')}`",
        f"**Calls:** {payload.get('n_generate')} · "
        f"**tokens** in={payload.get('prompt_tokens')} out={payload.get('candidates_tokens')} · "
        f"**est. USD** {payload.get('actual_usd_est')} "
        f"(within envelope: {payload.get('within_envelope')})",
        "",
        "## Taxonomy (Vertex)",
        "",
        f"```{tax}```",
        "",
        f"- Useful: **{payload.get('useful')}**",
        f"- Abstain OK: **{payload.get('abstain_ok')}**",
        f"- Wrong workstream: **{payload.get('wrong_ws')}**",
        "",
    ]
    if oc:
        lines += [
            "## Compare to prior Ollama density slice",
            "",
            f"| | Ollama (`{oc.get('model')}`) | Vertex |",
            "|---|---|---|",
            f"| Useful | {oc.get('useful')} | {payload.get('useful')} |",
            f"| Taxonomy | `{oc.get('taxonomy')}` | `{tax}` |",
            "",
        ]
    lines += [
        "## Revive-critical tokens after slice",
        "",
        "| ws | present | missing |",
        "|---|---|---|",
    ]
    for wid, info in (payload.get("revive_ready_after_slice") or {}).items():
        lines.append(
            f"| {wid} | {', '.join(info.get('present') or []) or '—'} | "
            f"{', '.join(info.get('missing') or []) or '—'} |"
        )
    lines += [
        "",
        "## Per-turn",
        "",
        "| id | class | proposed | need_ok | wrong_ws | notes |",
        "|---|---|---|---|---|---|",
    ]
    for r in payload.get("rows") or []:
        notes = ",".join((r.get("notes") or [])[:2])
        lines.append(
            f"| {r['id']} | {r['class']} | {len(r.get('proposed') or [])} | "
            f"{r.get('need_ok')} | {r.get('wrong_workstream')} | {notes} |"
        )
    lines += ["", "## Honest limits", "",
              "- Slice ≠ 200-turn live extract.",
              "- Gate/routing not under test here.",
              ""]
    RESULTS_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    payload = run()
    print(json.dumps({
        "status": payload.get("status"),
        "model": payload.get("model"),
        "project": payload.get("project"),
        "n_generate": payload.get("n_generate"),
        "actual_usd_est": payload.get("actual_usd_est"),
        "taxonomy": payload.get("taxonomy"),
        "useful": payload.get("useful"),
        "abstain_ok": payload.get("abstain_ok"),
        "wrong_ws": payload.get("wrong_ws"),
        "revive_ready": payload.get("revive_ready_after_slice"),
        "out": str(OUT.relative_to(ROOT)),
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
