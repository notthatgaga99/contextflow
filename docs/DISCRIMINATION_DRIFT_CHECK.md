# Discrimination path: literature check + stress test (drift vs direction)

**Date:** stress pass after two-channel policy table.  
**Question:** Is genre/identity bind for the working-memory switch an *extrapolated right direction*, or a *detour* away from Bet A?

---

## 1. Verdict (read this first)

| Question | Answer |
|----------|--------|
| Drifted from Bet A (switch, not memory SaaS)? | **No** — probes are bind CONTINUE/SWITCH/NEW/CLARIFY, not retrieval productization |
| Aligned with external research? | **Yes on the core claim** (similarity alone fails under shared domain; structure/identity first) |
| Math novelty? | **No** (TF–IDF / margins / disentanglement are known) |
| Application novelty (our bet)? | **Still yes** — those bits assembled as *frozen bind → L1-only generate* control law |
| Main risk of future detour | Becoming DST, discourse trees, or Mem0-class memory instead of sharpening bind→L1 |

**Bottom line:** Proceed. Treat casefile failures as calibration of the *I* channel, not a signal to abandon the model.

---

## 2. What we ran

```text
pytest -m trust                          → switch laws + hostile casefile + L1/generate siblings
python -m eval.discrimination.run_cases  → lexical casefile
# optional live (not CI):
. .\scripts\env_vertex_local.ps1
python -m eval.discrimination.vertex_smoke
```

Calibration fixes from this pass: (1) absolute identity floor under confusion;
(2) near-miss **before** underspecified stick so short “still getting 401” CLARIFYs.

Casefile buckets: near_miss_different, near_miss_clarify, surface_shift_same,
extension_same, common_concept_removed, true_new, underspecified_continue,
plus a **detour probe** (unrelated ML question must NEW — must not dump auth L1).

---

## 3. Literature map (application alignment)

| Source | Their claim | Ours | Alignment |
|--------|-------------|------|-----------|
| [CATD / thread disentanglement](https://aclanthology.org/D19-1682) (EMNLP’19) | Content similarity alone fails; need thread context / genre vs register | Genre confusion \(c_S\) vs identity \(d\) | **Same failure mode** |
| [Context-Agent discourse trees](https://aclanthology.org/2026.findings-acl.1472/) | Continue / create / switch branches; non-linear dialogue | CONTINUE / NEW / SWITCH (+ CLARIFY) | **Same control verbs** |
| [Beyond Similarity Search / Tenure](https://arxiv.org/html/2605.11325v1) | Cosine collapses in shared technical domain; BM25/alias beats vectors | Near-miss under shared `401`/`budget` | **Direct support** for anti-similarity-only bind |
| [STITCH / contextual intent](https://contextual-intent.github.io/) | Structure first, semantics second for memory retrieval | Identity first under high \(c_S\) | **Same ordering**; they apply to retrieval, we apply to **bind** |
| [AdaMem](https://arxiv.org/html/2603.16496v2) | Resolve participant/target before retrieval | Bind hop before L1 assemble | **Same shape**, different layer |
| [S3-DST](https://arxiv.org/pdf/2309.08827) | Segment dialogue + track state | We only need hop identity for switch | **Related but heavier** — full DST would be a detour |
| TF–IDF distinctive terms | Rare-in-corpus terms identify documents | IDF on Dist tokens | **Commodity tool**, correctly used |

**Reading:** The field is loudly saying “stop using one similarity score in a shared domain.” We did that *at the bind*, which is exactly where Bet A needs it. Extrapolation that *would* be a detour: rebuild AdaMem/STITCH/Context-Agent as the product.

---

## 4. What the stress test taught us (not vibes)

1. **Near-miss resolve works** when distinctive mass is real (JWT vs orders, Lisbon vs Paris, wedding vs trip budget).  
2. **Clarify was under-firing:** large \(\Delta_I\) with *tiny absolute* \(d\) (stray token `api` in “orders API”) looked like resolve.  
   **Fix:** under high \(c_S\), require \(d_{(1)} \ge \tau_{\mathrm{id\_abs}}\) else CLARIFY.  
3. **Extension / surface-shift / underspecified / true NEW** held on the casefile.  
4. **Detour probe passed:** unrelated “embeddings” question → NEW (does not stay on JWT to “summarize everything”).

That is evidence the application point is stable; the bug was calibration, not category error.

---

## 5. Drift radar (keep watching)

| Symptom | Means | Response |
|---------|-------|----------|
| Roadmap becomes “better memory tiers / graph RAG” | Sliding into acquihire memory lane | Cut; return to bind laws + L1 |
| Roadmap becomes full DST / discourse tree product | Stealing Context-Agent’s problem | Optional *behind* MemoryPort later; not the brand |
| Only LLM discern, drop \(c_S/\Delta_I\) audit | Unfalsifiable bind | Keep evidence struct mandatory |
| Casefile accuracy ↑ by overfitting cues | Theater | Grow adversarial rows; plot \((c_S,\Delta_I)\) |

---

## 6. How to re-run

```powershell
python -m eval.discrimination.run_cases --json eval/out/discrimination_cases.json
pytest -m trust -q
```

Study model: `docs/THREAD_DISCRIMINATION_MODEL.md`  
This drift check: `docs/DISCRIMINATION_DRIFT_CHECK.md`

---

## 7. Product call — LOCKED: clarify on weak near-miss

**Owner decision:** high genre confusion + weak identity → **CLARIFY**.

Rationale: Context management’s job is to bind without asking whenever
identity is recoverable (JWT cues, Alfama, stripe webhook, extension stick).
When the user prompts so thinly that only genre glue remains (“still getting
401”), asking which thread is the *least* harm — silent ACTIVE stick risks
wrong L1, which is worse than one clarify.

| Policy | Behavior | Status |
|--------|----------|--------|
| **clarify** | Ask which thread | **LOCKED default** (`CF_NEAR_MISS_WEAK=clarify`) |
| stick_active | Stay on ACTIVE silently | Escape hatch only (`CF_NEAR_MISS_WEAK=stick_active`) |

## 8. Recommended next (still on-path)

Hostile paraphrase / 3-way / L1-sibling rows are in `cases.jsonl` and
`tests/test_hostile_bind.py`. Optional live: `eval.discrimination.vertex_smoke`.

Slot/entity I-channel is in: unique `MemoryItem.slot` / `kind=entity` bind;
shared slot names stay genre (CLARIFY). Insights A/B:
`python -m eval.discrimination.insights`.

**Software insights from this slice**

1. Slots were already stored and used by L1 ranking; the binder only hashed
   `item.text`. `"what's the TTL?"` with text `"5 minutes"` + `slot=ttl` now hops.
2. Frozen-gate / referent-ambiguous **CLARIFY used to skip the I-channel**.
   Recoverable identity (Alfama entity) now resolves; weak 401 still asks.
3. Underspecified ACTIVE-stick must not undo `"no, the other one"` corrections.
4. Shared command verbs (`fix`) are not genre — `"fix that"` stays on the
   referent clock. Ten-workstream **p07** (gold ACT B) now ACTs instead of CLARIFY.

1. Durable real-process revive beyond FakeFirestore (live Firestore later).  
2. Optional embed contract into **I** — still two channels, same table.  
3. Do **not** pause switch work to build a memory SaaS.
