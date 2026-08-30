# Ten-workstream Vertex slice

**Integration demonstration** — not a statistical benchmark, not natural human behavior, and **not** a full 50-turn Vertex replay.

Vertex exercised the production-shaped **extract → writer → frozen routing → working-context → answer** path at five selected probes, while non-probe fixture history was seeded.

| Field | Value |
|---|---|
| Model | `gemini-2.5-flash-lite` |
| Region | `us-central1` |
| Embeddings | local (`CF_EMBED_LOCAL=1`) |
| Calls | **15** `generate_content` |
| Tokens | **5373** in / **6065** out |
| Est. cost | **~$0.002963** (Flash-Lite token table; not an invoice) |
| Cloud Run | not used ($0 attributable) |
| Correlation | `ten-ws-vertex-1cd18de661` |

## Seeding

Workstream cards come from `fixture.json`. Memory on non-probe turns was established with **Mock** extract scripts — not Vertex. Vertex extract / propose / answer ran only on turns **37, 38, 41, 48, 50**.

## Results (5 / 5)

| Probe | Gold | Vertex route | WC sufficient | Contam | Extract |
|---|---|---|---|---|---|
| p08 fix that | C ACT | CONTINUE C/C.loop1 | yes | none | empty (`[]`, OK for deictic) |
| p06 navy evening | E ACT | RETURN E/E.loop1 | yes | none | accepted → E |
| p11 long-gap A | A ACT | RETURN A/A.loop1 | yes | none | accepted → A |
| p15 deck / Lisbon | H ACT | RETURN H/H.loop1 | yes | none | accepted → H |
| p13 recent-trap C | C ACT | RETURN C/C.loop1 | yes | none | accepted → C |

**Wrong-ACT: 0. Critical missing state: 0. Contamination: 0.** Routing matched the local mock on all five probes.

## What this adds vs mock

| Layer | Mock 50-turn run | This slice |
|---|---|---|
| Historical memory | scripted | same Mock seed |
| Probe extract | scripts / empty | live `LlmMemoryExtractor` |
| Probe propose | scripted | live Vertex propose |
| Routing | frozen ContextFlow | same frozen ContextFlow |
| Answer | mock echo | live Vertex generate |

Empty extract on `fix that` is extraction behavior, not a resolver failure. Answer quality is not scored as a routing metric.

## Reproduce

```text
# mock stress (no Vertex)
python -m eval.ten_workstream.run

# five-probe Vertex slice (incurs cost; hard-capped at 15 calls)
python -m eval.ten_workstream.vertex_slice
```

## Limits

- Not a 50-turn hosted Vertex evaluation
- Not organic / consented chat evidence
- Not an extraction-quality or answer-quality benchmark
- Not production-scale reliability or auth proof
