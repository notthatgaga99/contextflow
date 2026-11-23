# Vertex 10×20 density revive harness

**Controlled engineering test** — not natural chat, not a statistical holdout.
Frozen gate. Mock-seeded history; live Vertex on 10 revive probes.

**Model:** `gemini-2.5-flash-lite` @ `contextflow-gagan-20261019` / `us-central1`
**Calls:** 37 / cap 48 · tokens in=22733 out=2845 · **est. USD ~0.003411** (per-million-token Flash-Lite rates; USD estimates use Flash-Lite list rates per *million* tokens ($0.1/1M in + $0.4/1M out). Not per-request; not an invoice.)
**Wall:** 59.119s · correlation `v10x20-gemini-2.5-flash-lite-4d7993f9`

## Summary

| Metric | Value |
|---|---|
| task_match | 10/10 |
| referent_match | 10/10 |
| policy_match | 10/10 |
| working_context_sufficient | 10/10 |
| wrong_act | 0 |
| mock route divergences | 0 |
| failure_layers | `{'NONE': 10}` |

## Per-probe

| probe | gold | vertex | task | policy | WC | wrong_act | extract | vs mock |
|---|---|---|---|---|---|---|---|---|
| r20_A | A/ACT | RETURN A | True | True | True | False | uncertain | same |
| r20_B | B/ACT | RETURN B | True | True | True | False | uncertain | same |
| r20_C | C/ACT | RETURN C | True | True | True | False | uncertain | same |
| r20_D | D/ACT | RETURN D | True | True | True | False | uncertain | same |
| r20_E | E/ACT | RETURN E | True | True | True | False | accepted | same |
| r20_F | F/ACT | RETURN F | True | True | True | False | accepted | same |
| r20_G | G/ACT | RETURN G | True | True | True | False | empty | same |
| r20_H | H/ACT | RETURN H | True | True | True | False | uncertain | same |
| r20_I | I/ACT | RETURN I | True | True | True | False | uncertain | same |
| r20_J | J/ACT | RETURN J | True | True | True | False | uncertain | same |

## Reproduce

```powershell
. .\scripts\env_vertex_local.ps1
python -m eval.ten_workstream.vertex_10x20_revive
```

## Limits

- History extracts are Mock scripts, not Vertex.
- Answer quality is not a routing metric.
- Do not retune TAU/DELTA from a single harness run.
