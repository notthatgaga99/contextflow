# Product demo (reviewer)

**CONTROLLED SYNTHETIC ENGINEERING DEMO** · **NOT A NATURAL-CHAT BENCHMARK**

## Launch

```bash
python -m eval.product_demo --serve
```

URL: http://127.0.0.1:8766/

Use `--no-browser` if you do not want an auto-opened tab.

## Flow

1. Read the one-sentence thesis on the first screen.
2. Click **PLAY SCENARIO** (or **STEP**).
3. At the hero: **CURRENT = navy**, **HISTORY = black superseded**, **EXCLUDED = unrelated**.
4. Final beat: **Maybe the navy one?** → **NEEDS CLARIFICATION**.

Full reviewer notes: [`docs/PRODUCT_DEMO.md`](../../docs/PRODUCT_DEMO.md).
