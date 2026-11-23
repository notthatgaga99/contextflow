"""Same 10×20 revive probes across all text Flash models on the project.

Skips image / TTS / live / omni variants. Each model runs extract+propose+answer
on the same 10 density revive probes (Mock-seeded history). Gate frozen.

Pricing is per-million tokens — full sweep of ~9 models is typically still cents.

  . .\\scripts\\env_vertex_local.ps1
  python -m eval.ten_workstream.vertex_10x20_model_sweep
  python -m eval.ten_workstream.vertex_10x20_model_sweep --models gemini-2.5-flash-lite,gemini-2.5-flash
"""

from __future__ import annotations

import argparse
import json
import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path

from eval.ten_workstream.vertex_10x20_revive import run as run_revive

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "eval" / "out" / "vertex_10x20_model_sweep.json"
RESULTS_MD = ROOT / "docs" / "VERTEX_10x20_MODEL_SWEEP.md"

SKIP_SUBSTR = ("image", "tts", "live", "omni", "native-audio")
# Gemini 3.x publisher models are global-only on this project; 2.5 stays regional.
GLOBAL_ONLY_PREFIXES = ("gemini-3",)
# Free Trial / express Gemini is ~10 RPM. With CF_VERTEX_MIN_INTERVAL_S=6.5,
# ~35 calls/model needs ~4+ min wall; allow headroom + 429 backoff.
MODEL_TIMEOUT_S = 900
MAX_ATTEMPTS = 5
PAUSE_BETWEEN_REGIONAL_S = 20
PAUSE_BETWEEN_GLOBAL_S = 60
RATE_LIMIT_NOTE = (
    "Paced for Free Trial / express ~10 RPM: GeminiClient spaces Vertex "
    "calls (default CF_VERTEX_MIN_INTERVAL_S=6.5). Extra pause between "
    "models (20s regional / 60s global). 429 → truncated exponential backoff."
)


def location_for_model(model: str) -> str:
    return "global" if model.startswith(GLOBAL_ONLY_PREFIXES) else "us-central1"


def _pause_after_model(region: str) -> None:
    wait = PAUSE_BETWEEN_GLOBAL_S if region == "global" else PAUSE_BETWEEN_REGIONAL_S
    print(f"  cool-down {wait}s ({region}) ...", flush=True)
    time.sleep(wait)


def list_text_flash_models(project: str, locations: tuple[str, ...] = ("us-central1", "global")) -> list[str]:
    from google import genai

    names: set[str] = set()
    for location in locations:
        client = genai.Client(vertexai=True, project=project, location=location)
        for m in client.models.list():
            n = (getattr(m, "name", None) or str(m)).split("/")[-1]
            if "gemini" not in n or "flash" not in n:
                continue
            if any(s in n for s in SKIP_SUBSTR):
                continue
            names.add(n)
    return sorted(names)


def _row_brief(payload: dict, *, region: str) -> dict:
    s = payload.get("summary") or {}
    return {
        "status": payload.get("status"),
        "model": (payload.get("models") or {}).get("lite"),
        "region": region,
        "calls": payload.get("calls"),
        "prompt_tokens": payload.get("prompt_tokens"),
        "candidates_tokens": payload.get("candidates_tokens"),
        "actual_usd_est": payload.get("actual_usd_est"),
        "elapsed_s": payload.get("elapsed_s"),
        "task_match": s.get("task_match"),
        "referent_match": s.get("referent_match"),
        "policy_match": s.get("policy_match"),
        "working_context_sufficient": s.get("working_context_sufficient"),
        "wrong_act": s.get("wrong_act"),
        "mock_route_divergences": s.get("mock_route_divergences"),
        "failure_layers": s.get("failure_layers"),
        "probes": [
            {
                "probe_id": r.get("probe_id"),
                "decision": r.get("decision"),
                "selected_task": r.get("selected_task"),
                "task_match": r.get("task_match"),
                "policy_match": r.get("policy_match"),
                "working_context_sufficient": r.get("working_context_sufficient"),
                "wrong_act": r.get("wrong_act"),
                "failure_layer": r.get("failure_layer"),
                "extract_status": r.get("extract_status"),
            }
            for r in (payload.get("probes") or [])
        ],
    }


def _is_retryable(exc: BaseException) -> bool:
    msg = str(exc)
    return any(
        tok in msg
        for tok in ("429", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "503", "deadline", "Timeout")
    )


def _backoff_s(attempt: int, exc: BaseException | None = None) -> float:
    """Truncated exponential backoff; honor Retry-Info seconds if present."""
    msg = str(exc or "")
    # google.api_core sometimes embeds "Please retry in 12.5s" / retryDelay
    import re

    m = re.search(r"[Rr]etry(?:\s+in|\s+after|Delay)?[^\d]*([\d.]+)\s*s", msg)
    if m:
        return min(300.0, max(15.0, float(m.group(1)) + 5.0))
    # attempt 1 → 30s, 2 → 60s, 3 → 120s, 4 → 240s (cap 300)
    return min(300.0, 30.0 * (2 ** (attempt - 1)))


def _run_model(model: str, region: str) -> dict:
    os.environ["CF_VERTEX_LOCATION"] = region
    os.environ["GCP_REGION"] = region
    # Ensure pace is on for Free Trial (caller may have cleared env).
    os.environ.setdefault("CF_VERTEX_MIN_INTERVAL_S", "6.5")
    last_exc: BaseException | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(run_revive, model=model, write_artifacts=False)
                payload = fut.result(timeout=MODEL_TIMEOUT_S)
            brief = _row_brief(payload, region=region)
            brief["error"] = None
            brief["attempts"] = attempt
            return brief
        except FuturesTimeout:
            last_exc = TimeoutError(f"model run exceeded {MODEL_TIMEOUT_S}s")
            print(f"  timeout attempt {attempt}/{MAX_ATTEMPTS}", flush=True)
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_ATTEMPTS and _is_retryable(exc):
                wait = _backoff_s(attempt, exc)
                print(
                    f"  retryable {type(exc).__name__} attempt {attempt}/{MAX_ATTEMPTS}; "
                    f"sleep {wait:.0f}s",
                    flush=True,
                )
                time.sleep(wait)
                continue
            raise
        if attempt < MAX_ATTEMPTS:
            wait = _backoff_s(attempt, last_exc)
            time.sleep(wait)
    assert last_exc is not None
    raise last_exc


def _finalize_payload(
    *,
    project: str,
    models: list[str],
    results: list[dict],
    regions_used: set[str],
    t0: float,
) -> dict:
    def _rank_key(r: dict) -> tuple:
        if r.get("status") != "ran":
            return (0, 0, 0, 0, 99.0)
        tm = str(r.get("task_match") or "0/0")
        try:
            ok, n = tm.split("/")
            tm_ratio = int(ok) / max(1, int(n))
        except Exception:
            tm_ratio = 0.0
        wcs = str(r.get("working_context_sufficient") or "0/0")
        try:
            wok, wn = wcs.split("/")
            wcs_ratio = int(wok) / max(1, int(wn))
        except Exception:
            wcs_ratio = 0.0
        return (
            1,
            tm_ratio,
            1 if int(r.get("wrong_act") or 0) == 0 else 0,
            wcs_ratio,
            -float(r.get("actual_usd_est") or 99),
        )

    ranked = sorted(results, key=_rank_key, reverse=True)
    total_usd = sum(float(r.get("actual_usd_est") or 0) for r in results if r.get("status") == "ran")
    total_calls = sum(int(r.get("calls") or 0) for r in results if r.get("status") == "ran")
    return {
        "status": "ran",
        "harness": "vertex_10x20_model_sweep",
        "project": project,
        "regions": sorted(regions_used),
        "location_policy": (
            "gemini-3* → global; else us-central1 "
            "(3.x 404 on regional publisher endpoints)."
        ),
        "rate_limit_note": RATE_LIMIT_NOTE,
        "models_requested": models,
        "n_models_ok": sum(1 for r in results if r.get("status") == "ran"),
        "n_models_error": sum(1 for r in results if r.get("status") == "error"),
        "total_calls": total_calls,
        "total_usd_est": round(total_usd, 6),
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "pricing_note": (
            "USD uses Flash-class list rates as $0.10/1M in + $0.40/1M out "
            "for estimate only — newer models may differ on the invoice."
        ),
        "leaderboard": [
            {
                "model": r.get("model"),
                "region": r.get("region"),
                "status": r.get("status"),
                "task_match": r.get("task_match"),
                "policy_match": r.get("policy_match"),
                "working_context_sufficient": r.get("working_context_sufficient"),
                "wrong_act": r.get("wrong_act"),
                "mock_route_divergences": r.get("mock_route_divergences"),
                "actual_usd_est": r.get("actual_usd_est"),
                "calls": r.get("calls"),
                "elapsed_s": r.get("elapsed_s"),
                "error": r.get("error"),
            }
            for r in ranked
        ],
        "results": results,
        "note": (
            "Same 10 density revive probes per model. Mock-seeded history. "
            "Frozen gate. Not natural chat."
        ),
    }


def _checkpoint(payload: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _write_md(payload)


def run_sweep(models: list[str] | None = None, *, merge_existing: bool = False) -> dict:
    os.environ.setdefault("CF_USE_VERTEX", "1")
    os.environ.setdefault("GCP_PROJECT", "contextflow-gagan-20261019")
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", os.environ["GCP_PROJECT"])
    os.environ.setdefault("CF_EMBED_LOCAL", "1")
    os.environ.setdefault("CF_VERTEX_MIN_INTERVAL_S", "6.5")

    project = os.environ["GCP_PROJECT"]
    if models is None:
        models = list_text_flash_models(project)

    prior: dict[str, dict] = {}
    if merge_existing and OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
            for r in old.get("results") or []:
                if r.get("status") == "ran" and r.get("model"):
                    prior[str(r["model"])] = r
        except Exception:
            prior = {}

    print(RATE_LIMIT_NOTE, flush=True)
    t0 = time.perf_counter()
    results: list[dict] = []
    regions_used: set[str] = set()
    for i, model in enumerate(models, 1):
        region = location_for_model(model)
        regions_used.add(region)
        if model in prior:
            print(f"[{i}/{len(models)}] {model} @ {region} ... MERGE prior OK", flush=True)
            results.append(prior[model])
            _checkpoint(_finalize_payload(
                project=project, models=models, results=results,
                regions_used=regions_used, t0=t0,
            ))
            continue
        print(f"[{i}/{len(models)}] {model} @ {region} ...", flush=True)
        try:
            brief = _run_model(model, region)
            results.append(brief)
            print(
                f"  OK {brief.get('task_match')} task | "
                f"wrong_act={brief.get('wrong_act')} | "
                f"${brief.get('actual_usd_est')} | "
                f"{brief.get('calls')} calls",
                flush=True,
            )
        except Exception as exc:
            results.append({
                "status": "error",
                "model": model,
                "region": region,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc()[-1500:],
            })
            print(f"  ERROR {type(exc).__name__}: {exc}", flush=True)
        _checkpoint(_finalize_payload(
            project=project, models=models, results=results,
            regions_used=regions_used, t0=t0,
        ))
        if i < len(models):
            _pause_after_model(region)

    payload = _finalize_payload(
        project=project, models=models, results=results,
        regions_used=regions_used, t0=t0,
    )
    _checkpoint(payload)
    return payload


def _write_md(payload: dict) -> None:
    regions = payload.get("regions") or [payload.get("region")]
    regions_s = ", ".join(f"`{r}`" for r in regions if r)
    lines = [
        "# Vertex 10×20 revive — model sweep",
        "",
        "Same controlled density revive probes across text Flash models available "
        f"on `{payload.get('project')}` ({regions_s}).",
        "",
        f"_{payload.get('location_policy')}_",
        "",
        f"_{payload.get('rate_limit_note')}_",
        "",
        f"**Models OK:** {payload.get('n_models_ok')} · "
        f"**errors:** {payload.get('n_models_error')} · "
        f"**total calls:** {payload.get('total_calls')} · "
        f"**est. USD sum:** ~{payload.get('total_usd_est')} · "
        f"**wall:** {payload.get('elapsed_s')}s",
        "",
        f"_{payload.get('pricing_note')}_",
        "",
        "## Leaderboard",
        "",
        "| model | region | task | policy | WC | wrong_act | $ est | calls | status |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in payload.get("leaderboard") or []:
        lines.append(
            f"| `{r.get('model')}` | {r.get('region')} | {r.get('task_match')} | "
            f"{r.get('policy_match')} | {r.get('working_context_sufficient')} | "
            f"{r.get('wrong_act')} | {r.get('actual_usd_est')} | {r.get('calls')} | "
            f"{r.get('status')} |"
        )
    err_rows = [r for r in (payload.get("results") or []) if r.get("status") == "error"]
    if err_rows:
        lines += ["", "## Errors", ""]
        for r in err_rows:
            lines.append(f"- `{r.get('model')}` @{r.get('region')}: {r.get('error')}")
    lines += [
        "",
        "## Reproduce",
        "",
        "```powershell",
        ". .\\scripts\\env_vertex_local.ps1",
        "python -m eval.ten_workstream.vertex_10x20_model_sweep",
        "```",
        "",
    ]
    RESULTS_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--models",
        default="",
        help="Comma-separated model ids (default: auto-list text Flash models)",
    )
    ap.add_argument(
        "--merge-existing",
        action="store_true",
        help="Keep prior OK rows from eval/out JSON for unknown/skipped models",
    )
    args = ap.parse_args()
    models = [m.strip() for m in args.models.split(",") if m.strip()] or None
    payload = run_sweep(models, merge_existing=args.merge_existing)
    print(json.dumps({
        "status": payload.get("status"),
        "n_models_ok": payload.get("n_models_ok"),
        "n_models_error": payload.get("n_models_error"),
        "total_calls": payload.get("total_calls"),
        "total_usd_est": payload.get("total_usd_est"),
        "elapsed_s": payload.get("elapsed_s"),
        "leaderboard": payload.get("leaderboard"),
        "out": str(OUT.relative_to(ROOT)),
        "md": str(RESULTS_MD.relative_to(ROOT)),
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
