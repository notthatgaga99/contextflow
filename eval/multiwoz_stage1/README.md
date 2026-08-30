# MultiWOZ two-stage eval (no production)

See **`docs/MULTIWOZ_TWO_STAGE_REPORT.md`** for the full writeup.

- `inspect.py` / `inspect.json` — utterance classes + DST depth histograms (DST not gold)
- `run.py` / `stage1.json` — Mock/lexical routing, no answer model
- `stage2.py` / `stage2.json` — 4 targets × full history / full task / compact, `llama3.1:8b` generate only
