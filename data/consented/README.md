# Consented conversation (local only)

Drop the **raw** transcript here. This directory is gitignored except this README and `session.schema.json`.

## Rules

- Owner-consented only. Do not copy WildChat, MultiWOZ, or anyone else’s logs.
- Strip names, addresses, phones, emails, credentials, API keys before saving.
- Do **not** rewrite the conversation to help ContextFlow.
- Do **not** insert task boundaries that were not in the original chat.

## Files

| File | Role |
|---|---|
| `session.json` | Raw turns (schema below). **Never commit.** |
| `session.sanitized.json` | Optional paraphrased copy if you need a shareable artifact |

After the file exists:

```
python -m eval.consented_case.run
```

Interpretation (human, not gold for routing math) lives in `docs/CONSENTED_INTERPRETATION.md` and a machine snapshot `eval/consented_case/interpretation.json` (also gitignored if it contains private detail; a paraphrased public sheet stays in `docs/`).
