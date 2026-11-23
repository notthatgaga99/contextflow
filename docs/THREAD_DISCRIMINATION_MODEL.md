# Thread discrimination model — study notes

**Status:** design + partial implementation. Read this before changing
`thread_discriminate.py` / `topic_align.py` thresholds.

**Product law (Bet A):** ContextFlow is a working-memory **switch**. Binding the
wrong near-miss thread is a category failure; L1 isolation cannot save you after
a wrong bind.

**Related code**

| Module | Role today |
|--------|------------|
| `app/router/thread_discriminate.py` | Contrastive scores \(o,d,s\); near-miss / stick helpers |
| `app/router/topic_align.py` | Post-gate lexical rail that *uses* those scores |
| `app/router/topic_discern.py` | Optional LLM discern + lexical veto |
| `app/router/gate.py` | Frozen binder (thresholds not retuned here) |
| `tests/test_thread_discrimination.py` | Trust cases for the four human scenarios |
| `docs/MEMORY_MANAGEMENT.md` | Planes + RB-WSR; discrimination is *routing*, not memory |

**How to use this doc**

1. Study §§1–5 until the two-channel idea is muscle memory.  
2. Skim §6 for the map to current code (what is real vs aspirational).  
3. Use §7–8 when adding cases or tuning.  
4. Only then change code (§9 continuation checklist).

---

## 1. The problem in one paragraph

Users produce messages that are **lexically close** to more than one open
workstream (shared genre: `401`, `hotel`, `budget`) while referring to **only
one identity** (JWT refresh vs orders checkout; Lisbon vs Paris). Separately,
they produce messages that look **lexically new** (wording shift, dropped nouns,
extra detail) while still meaning **the same** active thread.

A single similarity score cannot encode both facts. If you maximize “closeness,”
you glue near-misses. If you maximize “novelty → NEW,” you shatter continuations.
We need an explicit model of **shared confusion** vs **identity margin**.

---

## 2. Core thesis: two channels

Every message \(m\) and thread \(T_i\) should be scored in two views:

| Channel | Symbol | Intuition | Failure if used alone |
|---------|--------|-----------|------------------------|
| **Genre / shared** | \(S\) | “Same *kind* of problem” | JWT-auth glued to orders-401 |
| **Identity / referent** | \(I\) | “Which *instance*” | “also the TTL?” spuriously NEW |

**RB-WSR alignment:** retrieval relevance lives closer to \(S\); referent
resolution lives in \(I\). The binder may use \(S\) only when \(I\) is not in a
confusion regime.

**Informal law**

\[
\text{when many threads look close in } S,\text{ decide only with } I
\text{ (or CLARIFY if } I \text{ does not separate).}
\]

---

## 3. Notation and set construction

### 3.1 Tokens

Let \(\mathrm{tok}(\cdot)\) be the lexical tokenizer (stopwords removed, light
plural fold, including 3-letter identity tokens so `jwt` is not weaker than
`cart`). Current implementation: `_tokens` in `thread_discriminate.py`
(and the parallel helper in `topic_align.py`).

\[
M = \mathrm{tok}(m), \qquad
B_i = \mathrm{tok}(\mathrm{blob}(T_i))
\]

where \(\mathrm{blob}(T_i)\) concatenates title, goal, open loops, retrieval cues,
anchor decisions/constraints/entities, plus optional asserted memory texts.

### 3.2 Share and distinctive (open-set form)

Against the full open set \(\mathcal{T} = \{T_1,\ldots,T_N\}\):

\[
\begin{align}
\mathrm{Share}_i &= B_i \cap \bigcup_{k \neq i} B_k \\
\mathrm{Dist}_i  &= B_i \setminus \bigcup_{k \neq i} B_k
\end{align}
\]

**Interpretation**

- \(\mathrm{Share}_i\): vocabulary that cannot identify \(i\) among open threads
  (e.g. `401` if both auth and orders mention it).
- \(\mathrm{Dist}_i\): vocabulary unique to \(i\) in the current open set
  (e.g. `jwt`, `refresh` vs `orders`, `cart`).

**Pairwise form** (useful for analysis of two rivals \(i,j\)):

\[
\mathrm{Share}_{ij} = B_i \cap B_j, \quad
\mathrm{Dist}_i^{(j)} = B_i \setminus B_j, \quad
\mathrm{Dist}_j^{(i)} = B_j \setminus B_i.
\]

Open-set form is what the code uses; pairwise form is clearer on paper for
JWT vs orders.

### 3.3 Message hits (unweighted)

\[
\begin{align}
o_i &= \frac{|M \cap B_i|}{|M|}
  && \text{raw overlap (mixes } S \text{ and } I\text{)} \\
s_i &= \frac{|M \cap \mathrm{Share}_i|}{|M|}
  && \text{shared hit (“feels close”)} \\
d_i &= \frac{|M \cap \mathrm{Dist}_i|}{|M|}
  && \text{distinctive hit (“which one”)}
\end{align}
\]

These are exactly `overlap`, `shared_hit`, `distinctive` on `ThreadScores` today
(unweighted).

---

## 4. Aggregate statistics that drive decisions

### 4.1 Identity ranking and margin

Order threads by identity: \(d_{(1)} \ge d_{(2)} \ge \cdots\).

\[
\Delta_I = d_{(1)} - d_{(2)}
\]

- Large \(\Delta_I\): identity channel has a clear winner.  
- Tiny \(\Delta_I\): identity does not resolve — even if both look “close.”

Winner: \(i^\star = \arg\max_i d_i\) (ties → CLARIFY territory).

### 4.2 Shared confusion

Several equivalent definitions; pick one and stick to it in code + logs:

**Count form**

\[
C_S^{\#} = \big|\{ i : s_i \ge \tau_s \}\big|
\]

**Pair form** (often cleaner)

\[
c_S = \max_{i \neq j} \min(s_i, s_j)
\]

High \(c_S\) or \(C_S^{\#} \ge 2\): we are in a **near-miss regime** — many threads
match the genre of \(m\).

### 4.3 Active extension mass

Let \(a\) be ACTIVE. Extension / surface-shift / common-concept-removed all look like:

\[
d_a \ge \tau_{\mathrm{ext}}
\quad\text{and}\quad
d_{(1 \neq a)} < d_a + \delta_{\mathrm{rival}}
\]

i.e. ACTIVE still owns enough identity mass; no rival *leads* on \(I\).
Raw \(o_a\) may be mediocre — that is allowed.

---

## 5. Decision regions (the model to memorize)

Plot every turn in the plane \((c_S,\; \Delta_I)\) (or \((C_S^{\#},\; \Delta_I)\)).

```text
                 Δ_I high
            (identity clear)
                  │
     BIND i*      │     BIND i*
     (normal)     │     (near-miss OK:
                  │      genre confusing
                  │      but I separates)
  ────────────────┼──────────────────► c_S / C_S
   low confusion  │   high confusion
                  │
     CONTINUE /   │     CLARIFY
     EXTEND       │     (near-miss FAIL:
     (ACTIVE)     │      close & ambiguous)
     or keep gate │
                  │
                 Δ_I low
```

### 5.1 Policy table

Assume underspecified short follow-ups are handled first (stick ACTIVE) —
see `is_underspecified` in `topic_align.py`.

| Region | Condition (sketch) | Action |
|--------|-------------------|--------|
| Underspecified | short / deictic, ACTIVE exists | CONTINUE ACTIVE |
| Near-miss clarify | high confusion AND (\(\Delta_I < \varepsilon\) OR \(d_{(1)} < \tau_{\mathrm{id\_abs}}\)) | **CLARIFY** (product-locked: better than silent wrong L1; context mgmt still avoids ask when identity is recoverable) |
| Near-miss resolve | high confusion AND \(\Delta_I \ge \varepsilon\) | BIND \(i^\star\) by \(d\) (override weak gate) |
| Extend / same | \(d_a\) sufficient, rival not leading on \(d\) | CONTINUE ACTIVE (even if gate said NEW) |
| True NEW | \(\max d_i\) and \(\max o_i\) both low; not underspecified | NEW |
| Default | else | keep frozen gate decision |

**Critical rule:** In high shared confusion, **never** choose the winner by \(o_i\)
or by \(s_i\). Those are genre. Only \(d_i\) or CLARIFY.

### 5.2 Mapping to the four human scenarios

| Human scenario | Region | Signals |
|----------------|--------|---------|
| Seemingly close, different (JWT vs orders) | Near-miss resolve or clarify | High \(c_S\) (both hit `401`); \(d\) separates on `jwt`/`orders` |
| Seemingly different surface, same saga | Extend / same | \(d_a\) holds; wording change hurts \(o_a\) less than \(d_a\) |
| Extension needing more context | Extend / same | New detail tokens + residual \(d_a\); rival \(d\) not leading |
| Common concepts removed | Extend / same | \(s_a\) drops (no `401`) but \(d_a\) remains (`jwt`, `refresh`) |

---

## 6. IDF weighting (upgrade path — not fully in code yet)

Unweighted sets treat every token equally. `401` and `jwt` are not equal.

Define document frequency over **open threads**:

\[
\mathrm{df}(t) = |\{ i : t \in B_i \}|, \qquad
w(t) = \log \frac{1+N}{1+\mathrm{df}(t)}.
\]

Weighted hits:

\[
d_i^{w} = \frac{\sum_{t \in M \cap \mathrm{Dist}_i} w(t)}
              {\sum_{t \in M} w(t) + \epsilon},
\qquad
s_i^{w} = \frac{\sum_{t \in M \cap \mathrm{Share}_i} w(t)}
              {\sum_{t \in M} w(t) + \epsilon}.
\]

Effects:

- Tokens in many open threads (genre glue) get small \(w\) → weak identity.  
- Tokens in one thread get large \(w\) → strong identity.  
- Dropping a shared noun barely hurts \(d_a^{w}\); that is “common concepts removed.”

**Implementation note:** Replace unweighted \(d_i,s_i\) with \(d_i^{w},s_i^{w}\) inside
`score_threads` while keeping the same decision table. Log both for a while.

### 6.1 Optional embedding channels (later)

If using vectors, **do not** collapse to one cosine:

- \(S\): embed full blobs / genre spans.  
- \(I\): embed only Dist-side strings (or Dist-weighted tokens).  

Then redefine \(d_i,s_i\) as similarities in those spaces. Same decision table.

---

## 7. Bayesian reading (optional intuition)

\[
P(T_i \mid m) \propto P(m_I \mid \mathrm{id}_i)\,P(m_S \mid \mathrm{genre}_i)\,P(T_i)
\]

- \(P(m_I \mid \mathrm{id}_i)\): identity likelihood (~ \(d_i\)).  
- \(P(m_S \mid \mathrm{genre}_i)\): genre likelihood (~ \(s_i\)).  
- \(P(T_i)\): prior — boost ACTIVE, decay by turns since last mention.

Near-miss clarify ≈ posterior split across two threads with similar genre
likelihood and no identity dominance.  
Continue ≈ ACTIVE prior + non-leading rivals on identity.

This is not required in code; it justifies why ACTIVE bias and \(\Delta_I\) both appear.

---

## 8. What the code does today vs the model

### 8.1 Implemented (application layer)

The novelty is the **assembly**: frozen gate + two-channel math + L1 switch.
IDF/margins are standard; wiring them as bind law for RB-WSR is the product move.

| Model piece | Code |
|-------------|------|
| IDF-weighted \(d_i^{w}\), raw \(s\) for confusion | `score_threads` / `idf_weights` |
| Explicit \(c_S\), \(C_S^{\#}\), \(\Delta_I\), region | `DiscriminationEvidence` → `resolution_evidence["discrimination"]` |
| Single policy table | `decide_discrimination` (§5 regions) |
| `align_plan` | Thin adapter over `decide_discrimination` |
| High-\(C_S\) ⇒ bind \(\arg\max d\) or CLARIFY | `near_miss_*` regions + trust invariant |
| Slot / entity into \(I\) | `IdentityCues` from `MemoryItem.slot` + `kind=entity` |
| Gate CLARIFY through I-channel | Recoverable identity binds; deixis/correction keep clocks |
| Stick ACTIVE extension / underspecified | same policy table |
| Trust cases | `tests/test_thread_discrimination.py` (`pytest -m trust`) |
| LLM narrative of same laws | `build_discern_prompt` in `topic_discern.py` |

### 8.2 Still open

| Model piece | Gap |
|-------------|-----|
| Calibration casefile plotted in \((c_S,\Delta_I)\) | Started: `eval/discrimination/cases.jsonl` + `run_cases` |
| Absolute identity floor under confusion | Done: \(\tau_{\mathrm{id\_abs}}\) — weak \(d\) ⇒ CLARIFY even if \(\Delta_I\) large |
| Embedding / structured intent into **I** channel | Slot/entity cues wired (`IdentityCues`); embeddings still later |
| LLM discern same evidence schema | Partial (lexical path is Mock source of truth) |

**Drift check:** see [`DISCRIMINATION_DRIFT_CHECK.md`](DISCRIMINATION_DRIFT_CHECK.md) — field supports anti-similarity-only bind; detour = becoming DST/Mem0.

### 8.3 Honest limits

- Lexical \(\mathrm{tok}\) is brittle (synonyms, typos, multilingual).  
- Open-set \(\mathrm{Dist}_i\) **changes when threads open/close** — correct for
  discrimination among *current* rivals; do not cache Dist across sessions
  without recomputing.  
- LLM discern can disagree with lexical \(I\); veto exists but Vertex demos
  are not the Mock trust bar.  
- Wrong bind still cannot be fixed by L1 planes — discrimination is upstream
  of memory mastery.

---

## 9. Validation method (how we get better)

### 9.1 Case matrix (build this before more threshold tuning)

For each row: message, open cards (+ memory snippets), gold action
(`CONTINUE a` / `SWITCH i` / `CLARIFY` / `NEW`), and expected region.

Suggested columns:

`id | message | active | open_ids | gold | notes`

Minimum buckets (10+ each over time):

1. Near-miss different (shared genre, different identity)  
2. Surface-shift same  
3. Extension / more context same  
4. Common-concept-removed same  
5. True NEW  
6. Underspecified continue  

### 9.2 Plot

For each row compute \(c_S, \Delta_I, d_a, d_{(1)}\).  
If near-miss-different and same-saga overlap in that plane, **features** are
wrong — stop tuning \(\varepsilon\).

### 9.3 Regression bar

Keep Mock trust tests as invariants. Add new rows as tests that assert
**region + task_id**, not prose. Optional later: offline JSON casefile scored
by a tiny harness (no Vertex required).

---

## 10. Worked micro-examples

### 10.1 Near-miss different

- \(T_A\): jwt, auth, refresh, ttl, 401  
- \(T_C\): orders, cart, checkout, 401  
- \(m\): “JWT refresh still 401 — check TTL”

Then `401` ∈ Share; `jwt,refresh,ttl` ∈ Dist\(_A\).  
High \(s_A,s_C\), \(d_A \gg d_C\) → near-miss resolve → bind \(A\).

If \(m\): “still getting 401” only → high confusion, tiny \(\Delta_I\) → CLARIFY.

### 10.2 Common concepts removed

- \(m\): “refresh cookie path fails after rotating keys” (no `401`)  
- \(s\) drops; \(d_A\) still hits `refresh`/`cookie` → CONTINUE/SWITCH to \(A\),
  not orders.

### 10.3 Extension

- ACTIVE = Lisbon hotel; \(m\): “can we also check late checkout?”  
- Genre may weakly match “trip”; identity still on hotel/Lisbon memory →
  CONTINUE ACTIVE, not NEW outfit thread.

---

## 11. Continuation checklist (when we resume coding)

Do in order; do not skip to “smarter LLM.”

1. **Evidence struct** on every align/discriminate decision:  
   `{s_i, d_i, o_i, c_S, Delta_I, region, winner}` in `resolution_evidence`.  
2. **IDF weights** inside `score_threads`; keep unweighted in logs for diff.  
3. **Rewrite `align_plan` branches** to the policy table in §5.1 (one place).  
4. **Hard invariant test:** if \(c_S\) high, final task_id must equal
   \(\arg\max d_i\) or CLARIFY — never gate’s \(o\)-winner when it disagrees.  
5. **Casefile** `eval/discrimination/cases.jsonl` + scorer; grow from trust tests.  
6. Only then: embedding identity channel or tighter LLM discern — still two
   channels, same table.

---

## 12. Glossary

| Term | Meaning |
|------|---------|
| Genre / shared (\(S\)) | Cross-thread common vocabulary / problem family |
| Identity (\(I\)) | Thread-unique vocabulary / instance cues |
| Near-miss | High shared confusion; identity must separate or CLARIFY |
| Extension | Same thread, more detail / context needed |
| Surface-shift | Same thread, different wording |
| Common-concept-removed | Shared glue words absent; distinctive remains |
| Frozen gate | `gate.py` thresholds; discrimination is post-gate rail |
| Trust suite | `pytest -m trust` — Mock adoption bar for switch laws |

---

## 13. One-page cheat sheet

```text
CLOSE ≠ SAME.
  close  := high shared confusion (genre)
  same   := identity mass on one thread (esp. ACTIVE)
  different near-miss := high confusion + (Δ_I large → bind d*) 
                         or (Δ_I small → CLARIFY)
  never bind by raw overlap alone under high confusion

CONTINUE when ACTIVE wins or ties identity without rival lead,
even if the sentence looks new or drops shared nouns.

NEW only when identity and overlap are both weak (and not underspecified).

Memory planes enforce L1 after bind.
This model is what makes the bind worth enforcing.
```

---

*Last updated: discrimination math study pass. Implementation tracks §8 and §11.*
