# Reproduce the ContextFlow PoC

Git root is the inner `contextflow` directory (the folder that contains `app/`
and `.git`), not the parent workspace folder.

```powershell
cd "c:\Users\emxxgag\OneDrive - Ericsson\Documents\CodeBase\contextflow\contextflow"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

On Unix: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.

Copy `.env.example` to `.env` only if you need Gemini. **Do not commit `.env`.**
Do not put API keys in the repo.

Default runtime is MockLLM. Tests must pass with no network and no GPU.

---

## A. $0 MockLLM (no cloud)

These do not call Vertex or Gemini.

```powershell
pytest -q
python -m app
python -m eval.task_count_scale
```

Optional Mock-only eval (also $0):

```powershell
python -m eval.referent_controlled
python -m eval.context_sufficiency
```

`python -m eval.context_sufficiency` runs Mock rows always; it may also try
Ollama if a local daemon is up (see B).

Expected demo (`python -m app`): interleaved A→B→C then
`"okay fix that authentication thing"` routes back to task A (RETURN/SWITCH
depending on pause/COLD), not the most recent task.

Scale experiment writes `eval/out/task_count_scale.json` (gitignored).

---

## B. Local Ollama (no Vertex billing)

Requires a local Ollama daemon and already-pulled models. **Do not pull extra
models** unless you choose to; the PoC used:

- `qwen2.5:1.5b` — weak local answer / provider check
- `llama3.1:8b` — stronger local answer check (~4.9 GB)

```powershell
$env:CF_USE_OLLAMA='1'
$env:OLLAMA_BASE_URL='http://127.0.0.1:11434'
$env:OLLAMA_MODEL='qwen2.5:1.5b'
python -m eval.context_sufficiency
```

Stronger answer model (local disk/RAM only; **not** Vertex):

```powershell
$env:OLLAMA_MODEL='llama3.1:8b'
python -m eval.context_model_strength
```

Outputs: `eval/out/context_sufficiency.json`, `eval/out/context_model_strength.json`
(gitignored). Routing in those probes used MockLLM proposals + frozen production
resolver/gate; Ollama was the **answer** model.

Unit tests (`pytest -q`) must not require Ollama.

---

## C. Vertex Gemini (usage-billed)

**Vertex AI inference requests are usage-billed according to the model's token
pricing. Do not run the large validation suite unless intentionally reproducing
the experiment.**

The PoC already recorded one full run. Re-running `python -m eval.gemini_validation`
will spend additional credits (~135 `generate_content` calls at temperature 0).

Credentials: Application Default Credentials (`gcloud auth application-default login`)
or a key you keep **only** in `.env` as `GEMINI_API_KEY`. Never commit credentials.
Enable `aiplatform.googleapis.com` on the project if Vertex returns 403.

The recorded experiment used:

```powershell
$env:CF_USE_VERTEX='1'
$env:GCP_PROJECT='YOUR_PROJECT'          # do not commit a key; project id is not a secret by itself
$env:GCP_REGION='us-central1'            # 2.0-flash-lite was unavailable in asia-south1 on the PoC project
$env:CF_LITE_MODEL='gemini-2.5-flash-lite'
python -m eval.gemini_validation
```

Construction tests **do not** call Gemini:

```powershell
pytest -q tests/test_gemini_validation.py
```

Smoke is 3 ContextFlow proposes; full suite is 128 scale cells + 4 exp2 cells
plus those 3 smoke calls (135 proposes). Generate and embed are skipped.
Baselines do not call Gemini.

If you only need the published numbers, read `eval/out/POC_RESULTS.md` instead
of re-running.

---

## What not to change when reproducing

Do not retune `TAU` / `DELTA` / `HYST` / `W_*`. Do not patch the 401 sibling
case. Do not swap hash embeddings for Vertex embeddings if you want the same
attribution (provider = Gemini propose only).
