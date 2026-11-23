# Vertex 10×20 revive — model sweep

Same controlled density revive probes across text Flash models available on `contextflow-gagan-20261019` (`global`, `us-central1`).

_gemini-3* → global; else us-central1 (3.x 404 on regional publisher endpoints)._

_Paced for Free Trial / express ~10 RPM: GeminiClient spaces Vertex calls (default CF_VERTEX_MIN_INTERVAL_S=6.5). Extra pause between models (20s regional / 60s global). 429 → truncated exponential backoff._

**Models OK:** 8 · **errors:** 0 · **total calls:** 296 · **est. USD sum:** ~0.029251 · **wall:** 2106.184s

_USD uses Flash-class list rates as $0.10/1M in + $0.40/1M out for estimate only — newer models may differ on the invoice._

## Leaderboard

| model | region | task | policy | WC | wrong_act | $ est | calls | status |
|---|---|---|---|---|---|---|---|---|
| `gemini-2.5-flash` | us-central1 | 10/10 | 10/10 | 10/10 | 0 | 0.00329 | 37 | ran |
| `gemini-2.5-flash-lite` | us-central1 | 10/10 | 10/10 | 10/10 | 0 | 0.003479 | 37 | ran |
| `gemini-3.5-flash-lite` | global | 10/10 | 10/10 | 10/10 | 0 | 0.003573 | 37 | ran |
| `gemini-3.6-flash` | global | 10/10 | 10/10 | 10/10 | 0 | 0.003668 | 37 | ran |
| `gemini-3-flash-preview` | global | 10/10 | 10/10 | 10/10 | 0 | 0.003677 | 37 | ran |
| `gemini-3.7-flash` | global | 10/10 | 10/10 | 10/10 | 0 | 0.003708 | 37 | ran |
| `gemini-3.1-flash-lite` | global | 10/10 | 10/10 | 10/10 | 0 | 0.003916 | 37 | ran |
| `gemini-3.5-flash` | global | 10/10 | 10/10 | 10/10 | 0 | 0.00394 | 37 | ran |

## Reproduce

```powershell
. .\scripts\env_vertex_local.ps1
python -m eval.ten_workstream.vertex_10x20_model_sweep
```
