# ContextFlow concepts — study & review guide

**Purpose:** One place to learn everything we locked in this arc: Bet A, kernel E2E,
memory planes, thread discrimination (genre vs identity), and clarify policy.

**How to use:** Read top-to-bottom once. Re-run the commands in §9 until they stay green.
Then re-read §3–§5 slowly — that is the product brain.

---

## 1. Product bet (do not forget)

| Locked | Meaning |
|--------|---------|
| **Bet A** | Product = **working-memory switch**, not chat agent, not memory SaaS |
| **Threat** | “Memory layers” get absorbed by bigcos — we do not compete there |
| **Claim** | When users jump topics, bind **one** hop; generate sees **only** that hop’s L1 |
| **Novelty** | Not new math — the **assembly** of bind + two-channel discrimination + L1 law |

One sentence: *Relevance ≠ resolution; genre closeness ≠ thread identity.*

---

## 2. End-to-end turn (kernel)

```text
message
  → plan (frozen gate)
  → post-gate discrimination / topic align   ← genre S vs identity I
  → NEW: create card → extract → answer
    else: extract → execute (answer)
  → SHORT_TERM L1 snapshot (l1_expose)
  → generate from that package
```

| Piece | Code |
|-------|------|
| Canonical door | `app/kernel/session.py` → `run_kernel_turn` |
| Pipeline | `app/turn_pipeline.py` |
| Binder + package | `app/engine.py` |
| HTTP | `POST /turn`, `POST /agent/turn` (both use kernel) |

**Honesty rules we implemented**

1. NEW: extract **before** answer so same-turn facts can enter L1.  
2. `TurnResult.l1_expose` = what generate used; kernel prefers it for diagnostics.  
3. Agent tools run **after** answer; they never re-bind.

---

## 3. Memory planes (RB-WSR)

See also `MEMORY_MANAGEMENT.md`.

| Plane | Role |
|-------|------|
| **SHORT_TERM (L1)** | Only surface `generate()` may read |
| **LONG_TERM** | Asserted semantic / episodic |
| **PROCEDURAL** | How-to `procedure` items |
| **RELEVANT** | Bound cold enrich only (never multi-thread top-k) |
| **INDEX** | Open cards for routing — not L1 body |
| **ARCHIVE** | Opt-in import only |

Hard rules: binder picks hop; RELEVANT cannot replace binder; ARCHIVE never auto-merges.

---

## 4. Thread discrimination (the math you apply)

Full model: `THREAD_DISCRIMINATION_MODEL.md`. Drift check: `DISCRIMINATION_DRIFT_CHECK.md`.

### 4.1 Two channels

| Channel | Symbol | What | Failure if used alone |
|---------|--------|------|------------------------|
| Genre / shared | \(S\) | “Same *kind* of problem” (`401`, `hotel`, `budget`) | Glues JWT to orders |
| Identity | \(I\) | “Which *instance*” (`jwt`/`refresh` vs `orders`/`cart`) | Misses “also the TTL?” |

### 4.2 Scores (per open thread \(T_i\))

- \(o_i\) — raw overlap (mixed; debug)  
- \(s_i\) — shared hit (**raw** used for confusion — IDF would hide `401`)  
- \(d_i\) — distinctive hit (**IDF-weighted** — rare tokens win)  
- \(c_S\) — shared confusion (pair form / count)  
- \(\Delta_I = d_{(1)} - d_{(2)}\) — identity margin  

Code: `app/router/thread_discriminate.py` → `score_threads`, `build_evidence`, `decide_discrimination`.

### 4.3 Decision regions (policy table)

| Situation | Action |
|-----------|--------|
| High \(c_S\), weak \(d\) or tiny \(\Delta_I\) | **CLARIFY** (product-locked) |
| High \(c_S\), strong \(d_{(1)}\) | Bind \(\arg\max d\) (near-miss resolve) |
| ACTIVE still owns identity / extension | CONTINUE ACTIVE (even if gate said NEW) |
| Underspecified, **not** confused | Stick ACTIVE (`yml?`, `ok?`) |
| Both \(d\) and \(o\) weak | NEW |
| Else | Keep frozen gate |

**Never** bind by raw overlap alone under high confusion.

### 4.4 Four human scenarios

1. **Close but different** — shared genre, different identity → resolve by \(d\) or CLARIFY  
2. **Surface looks new, same saga** → CONTINUE  
3. **Extension / more context** → CONTINUE (not NEW)  
4. **Common concepts removed** — drop `401`, keep `jwt`/`refresh` → still auth  

### 4.5 Clarify policy (your lock)

Context management should **avoid asking** when identity is recoverable.  
When the user prompts so thinly that only genre glue remains → **CLARIFY** is the least harm (wrong silent L1 is worse).

Escape hatch only: `CF_NEAR_MISS_WEAK=stick_active`.

Clarify copy prefers the confused pair from `discrimination.winner_id` / `second_id`.

---

## 5. Frozen gate vs rails

| Layer | Role |
|-------|------|
| `gate.py` / scorer | Frozen thresholds — science baseline |
| `thread_discriminate` / `topic_align` | Post-gate **application rail** (does not retune gate) |
| `topic_discern` | Optional LLM narrative + lexical veto (`CF_TOPIC_LLM`) |

Evidence always logged: `resolution_evidence["discrimination"]` with \(c_S\), \(\Delta_I\), region, per-thread scores.

---

## 6. Trust & casefile (how we know it works)

| Command | What |
|---------|------|
| `pytest -m trust -q` | Switch laws + casefile + hostile L1 + slot/entity I-channel |
| `pytest -m integration -q` | Kernel + FakeFirestore revive (including slot hops) |
| `python -m eval.discrimination.run_cases --json eval/out/discrimination_cases.json` | Offline case matrix |

Casefile: `eval/discrimination/cases.jsonl`  
Buckets: near_miss_different, near_miss_clarify, surface_shift_same, extension_same, common_concept_removed, true_new, underspecified_continue, synonym/3-way, detour probe.

---

## 7. Literature stance (why this is not a detour)

Field agrees: **similarity alone fails in a shared domain** (thread disentanglement, Tenure/anti-cosine, STITCH “structure first”).  
We apply that at **bind**, then enforce with L1 — Bet A.

Detours to refuse: becoming Mem0/DST/discourse-tree **product**; selling “memory layers.”

---

## 8. Concept map (cheat sheet)

```text
USER MESSAGE
    │
    ├─ GATE (frozen) ──► proposal hop
    │
    └─ DISCRIMINATION (S vs I)
           │
           ├─ high C_S + weak I  → CLARIFY  (ask; least harm)
           ├─ high C_S + strong I → BIND argmax d
           ├─ extension / surface-shift → CONTINUE active
           └─ weak all → NEW
    │
    ▼
EXTRACT (Writer) → MEMORY PORT
    │
    ▼
ASSEMBLE L1 (bound only) → generate(L1 + message)
    │
    ▼
PLANES diagnostics (UI); tools after (never re-bind)
```

---

## 9. Review checklist (you)

- [ ] Explain Bet A in one sentence without saying “memory product”  
- [ ] Draw extract→bind→L1 for NEW vs non-NEW  
- [ ] Define \(c_S\) and \(\Delta_I\); when CLARIFY vs resolve  
- [ ] Give an example of close-but-different and common-concept-removed  
- [ ] Name what generate is allowed to see  
- [ ] Run `pytest -m trust -q` and casefile scorer green  
- [ ] Read `discrimination` blob on a CLARIFY turn (winner/second/region)  

---

## 10. File index

| Doc / module | Topic |
|---------------|--------|
| This file | Study overview |
| `THREAD_DISCRIMINATION_MODEL.md` | Full math |
| `DISCRIMINATION_DRIFT_CHECK.md` | Literature + product lock |
| `MEMORY_MANAGEMENT.md` | Planes |
| `app/kernel/session.py` | E2E door |
| `app/router/thread_discriminate.py` | Policy table |
| `app/router/topic_align.py` | Adapter |
| `eval/discrimination/` | Casefile + runner |
| `tests/test_trust_suite.py` | Switch laws |
| `tests/test_thread_discrimination.py` | Discrimination + clarify E2E |
| `tests/test_discrimination_cases.py` | Casefile in CI trust |

---

*When something feels like “memory feature creep,” re-read §1 and §7.*
