# Extract density under 10×20 cues (Vertex Flash-Lite)

**CONTROLLED density-extract slice** — not natural chat, not production accuracy.
No routing. Writer validates. Structured `propose()` + schema.

**Model:** `gemini-2.5-flash-lite` @ `contextflow-gagan-20261019` / `us-central1`
**Calls:** 9 · **tokens** in=6716 out=721 · **est. USD** 0.00096 (within envelope: True)

## Taxonomy (Vertex)

```{'USEFUL': 10, 'ABSTAIN_OK': 2}```

- Useful: **10**
- Abstain OK: **2**
- Wrong workstream: **0**

## Compare to prior Ollama density slice

| | Ollama (`llama3.1:8b`) | Vertex |
|---|---|---|
| Useful | 2 | 10 |
| Taxonomy | `{'EMPTY_FAIL': 8, 'USEFUL': 2, 'ABSTAIN_FAIL': 1, 'ABSTAIN_OK': 1}` | `{'USEFUL': 10, 'ABSTAIN_OK': 2}` |

## Revive-critical tokens after slice

| ws | present | missing |
|---|---|---|
| A | 5, api.internal | — |
| B | debian, 4 | — |
| E | navy, peplum | — |

## Per-turn

| id | class | proposed | need_ok | wrong_ws | notes |
|---|---|---|---|---|---|
| d04_E_black | USEFUL | 1 | True | False |  |
| d01_A_ttl15 | USEFUL | 1 | True | False |  |
| d02_B_alpine | USEFUL | 1 | True | False |  |
| d03_C_gateway | USEFUL | 1 | True | False |  |
| d05_E_navy_corr | USEFUL | 1 | True | False | deterministic_correction |
| d06_A_ttl5 | USEFUL | 2 | True | False |  |
| d07_B_debian | USEFUL | 1 | True | False |  |
| d10_E_peplum | USEFUL | 1 | True | False |  |
| d08_A_aud | USEFUL | 1 | True | False |  |
| d09_B_4gi | USEFUL | 1 | True | False |  |
| d11_A_recall_abstain | ABSTAIN_OK | 0 | True | False | recall_only_no_new_assert |
| d12_A_revive_abstain | ABSTAIN_OK | 0 | True | False | recall_only_no_new_assert |

## Honest limits

- Slice ≠ 200-turn live extract.
- Gate/routing not under test here.
