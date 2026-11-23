# Organic-shaped eval slice (authored)

**Not** real human logs. **Not** production accuracy. Gate frozen — do not retune TAU/W_*.

| Field | Value |
|-------|--------|
| `kind` | `authored_organic_shaped` |
| `human_behavior` | `false` |
| Purpose | Small interleaved holdout (2–3 hops) scored with layered metrics |

```powershell
python -m eval.organic.run
pytest -m organic -q
```

Gold lives only under `eval/organic/`. Runtime `app/` never imports it.
