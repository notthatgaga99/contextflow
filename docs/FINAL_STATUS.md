# ContextFlow — Final status (Phase 14 cleanup)

**Internal release hygiene report.** Not a natural-chat benchmark. **Not production-ready.**

**Routing / MemoryWriter freeze:** `8cc553983b45702ff16c071678f9bdc5b9d26fe3`  
**GCP tip:** image `contextflow-durable:poc6-phase14` · revision end `contextflow-durable-00029-h74`  
**Authoritative cloud rollup:** `eval/out/phase14_gcp_validation.json` (gitignored; regenerate via harnesses)

---

## DEMONSTRATED

### Local product demo (offline MockLLM)
- One-window leave/return narrative; 15 beats; hero “Okay, back to the outfit.”
- CURRENT = navy; HISTORY = black superseded; unrelated EXCLUDED
- “Maybe the navy one?” → NEEDS CLARIFICATION
- Deterministic reset/replay; no GCP/Vertex/credentials/network required
- Command: `python -m eval.product_demo --serve` → http://127.0.0.1:8766/

### Cloud research POC (authenticated Cloud Run)
- Path: HTTP → Vertex extract → MemoryWriter → Firestore memory + registry → frozen routing → WorkingContext → Vertex answer → revision replacement → reconstruction
- Correction extraction **10/10**; supersession **10/10**; duplicate current decisions **0**; working context **10/10**; contamination **0**
- Isolation **10/10 HTTP 200 / 0 leaks** (rate-limit retries only)
- Dynamic NEW creation **10/10**; memory persistence pre-restart **10/10**; revision survival **9/10**; return **9/10** error-free (1× Vertex 429)
- Routing and MemoryWriter unchanged vs freeze checkpoint

---

## TESTED

- Local: `pytest -q` (full suite)
- Product demo: `tests/test_product_one_window.py` including HTTP `TestClient` path
- Cloud harnesses (cost): `end_to_end_resurrection`, `e2e_repeatability`, `dynamic_workstream_e2e`
- Security boundaries: no `app/` → `eval` imports; no service-account JSON in tree; Cloud Run durable service authenticated

---

## KNOWN LIMITATIONS

- Dynamic revision survival **9/10** under Vertex `429 RESOURCE_EXHAUSTED` (post-restart answer); not claimed as 10/10
- Frozen cue/recency routing: sparse/overlapping language may CONTINUE/SWITCH — see `docs/PHASE14_TURN3_FORENSIC.md`
- Synthetic / adversarial fixtures; not organic multi-user chat
- Single-region Firestore; no production SLO / HA claim
- Cost figures are harness estimates, not invoices

---

## NOT PRODUCTION READY

Do **not** claim: production readiness, organic-chat accuracy, answer-quality superiority, statistical holdout generalization, or that the local MockLLM demo proves hosted-model behavior.

Reviewer entry points:
- Local: `docs/PRODUCT_DEMO.md`
- Cloud: `docs/CLOUD_POC_REVIEWER.md`
