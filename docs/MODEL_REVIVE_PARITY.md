# Model revive parity (CF package × Lite vs Flash)

**Integration demonstration — not a statistical benchmark, not natural chat.**

**Date:** 2026-09-10  
**Basic model:** `gemini-2.5-flash-lite`  
**Good model:** `gemini-2.5-flash`  
**Calls:** 8 / 8  
**Est. cost (token table):** ~$0.0005  

## Claim under test

Given the **same ContextFlow working-context package** on revive probes, a basic Flash-Lite answer model recovers needed state at a similar rate to Flash — so the revive is carried by the layer, not by model size.

## Summary

| Metric | Lite | Flash |
|---|---|---|
| Clean hits (needed all present, no leak/stale) | **2/4** | **1/4** |
| Mean needed-state hit rate | **62%** | **50%** |
| Mean CF prompt chars | 385 | (same package) |
| Mean FULL prompt chars (ref) | 723 | (not answered) |

**Parity gap (Flash − Lite clean hits):** −1 (Lite ≥ Flash on this slice)

### How to use this in the write-up

- Same CF package → Lite and Flash both land the **navy correction revive** cleanly (3/3 cues).
- Lite is **not** systematically worse; on this fixture it matches or beats Flash on state recovery.
- Package is ~**half** the FULL transcript size (~385 vs ~723 chars) while still enabling revive.
- Do **not** claim “Lite equals Pro on quality” — claim **revive state recovery parity under CF packaging**.

## Per-probe

| Probe | CF chars | FULL chars | Lite hit | Flash hit | Lite clean | Flash clean |
|---|---|---|---|---|---|---|
| return_dress_before_correction | 376 | 600 | 0/2 | 1/2 | False | False |
| return_jwt | 356 | 661 | 1/2 | 1/2 | False | False |
| return_navy_correction | 431 | 783 | 3/3 | 3/3 | True | True |
| return_navy_again | 377 | 851 | 3/3 | 0/3 | True | False |

## Limits

- Synthetic ABCD fixture; Mock extract for history
- Answer cues = string presence of needed_state (not human preference)
- Flash may emit longer prose or refuse when package is thin; we score state recovery, not eloquence
- Pro / Gemini 3.x not included (cost + claim scope)
- Early dress/JWT probes show thin-package behavior on **both** models — not Lite-specific

## Reproduce

```text
CF_MODEL_PARITY=1 python -m eval.model_revive_parity
```
