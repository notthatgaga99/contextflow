# Extract density under 10×20 cues (local Ollama)

**CONTROLLED density-extract slice** — not natural chat, not production accuracy.
No Vertex. No ContextFlow routing. Writer validates. Gate frozen / unused.

**Model:** `llama3.1:8b` · generates: **12** · elapsed **473.43s**

## Taxonomy

```{'EMPTY_FAIL': 8, 'USEFUL': 2, 'ABSTAIN_FAIL': 1, 'ABSTAIN_OK': 1}```

- Useful: **2**
- Abstain OK: **1**
- Wrong workstream: **0**

## Revive-critical tokens after slice (L2 projection)

| ws | present | missing |
|---|---|---|
| A | aud | 5 |
| B | — | debian, 4 |
| E | — | navy, peplum |

## Per-turn

| id | turn | class | proposed | need_ok | ws wrong | recon |
|---|---|---|---|---|---|---|
| d04_E_black | 5 | EMPTY_FAIL | 0 | False | False | missing_required |
| d01_A_ttl15 | 11 | EMPTY_FAIL | 0 | False | False | missing_required |
| d02_B_alpine | 12 | USEFUL | 1 | True | False | ok |
| d03_C_gateway | 13 | EMPTY_FAIL | 0 | False | False | missing_required |
| d05_E_navy_corr | 35 | EMPTY_FAIL | 0 | False | False | missing_required |
| d06_A_ttl5 | 41 | EMPTY_FAIL | 0 | False | False | missing_required |
| d07_B_debian | 42 | EMPTY_FAIL | 0 | False | False | missing_required |
| d10_E_peplum | 45 | EMPTY_FAIL | 0 | False | False | missing_required |
| d08_A_aud | 61 | USEFUL | 1 | True | False | ok |
| d09_B_4gi | 72 | EMPTY_FAIL | 0 | False | False | missing_required |
| d11_A_recall_abstain | 131 | ABSTAIN_FAIL | 1 | True | False | n/a |
| d12_A_revive_abstain | 191 | ABSTAIN_OK | 0 | True | False | n/a |

## Honest limits

- Slice ≠ full 200-turn extract cost/quality.
- Small local models often mis-anchor workstream ids (see prior 1.5b results).
- Cloud Free Trial (legitimate first signup only) is optional for Vertex compare — not required for this measurement.
