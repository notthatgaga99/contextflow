"""Inspect the unlabeled interleaved pilot corpus. No engine, no LLM, no network."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent / "interleaved_corpus"
REQUIRED_SESSION_KEYS = {
    "session_id",
    "archetype",
    "label_status",
    "source",
    "human_behavior",
    "interleaving",
    "domains_present",
    "workstreams",
    "turns",
    "probe_candidates",
}
FORBIDDEN_GOLD_KEYS = {
    "gold_task_id",
    "gold_referent_id",
    "gold_decision",
}


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def validate_session(data: dict, filename: str) -> list[str]:
    errors: list[str] = []
    missing = REQUIRED_SESSION_KEYS - set(data)
    if missing:
        errors.append(f"{filename}: missing keys {sorted(missing)}")
    if data.get("label_status") != "unlabeled":
        errors.append(f"{filename}: expected label_status=unlabeled for pilot 0")
    if data.get("human_behavior") is True:
        errors.append(f"{filename}: synthetic pilot must not claim human_behavior")
    if FORBIDDEN_GOLD_KEYS & set(data):
        errors.append(f"{filename}: gold fields on session root are not allowed in pilot 0")
    turns = data.get("turns") or []
    ids = [t.get("turn_id") for t in turns]
    if ids != list(range(1, len(turns) + 1)):
        errors.append(f"{filename}: turn_id must be contiguous 1..n")
    for t in turns:
        if FORBIDDEN_GOLD_KEYS & set(t):
            errors.append(f"{filename}: turn {t.get('turn_id')} has gold fields (pilot 0 is unlabeled)")
        if t.get("role") not in {"user", "assistant"}:
            errors.append(f"{filename}: turn {t.get('turn_id')} bad role")
        if not str(t.get("text") or "").strip():
            errors.append(f"{filename}: turn {t.get('turn_id')} empty text")
    for p in data.get("probe_candidates") or []:
        if FORBIDDEN_GOLD_KEYS & set(p):
            errors.append(f"{filename}: probe_candidate has gold fields")
        tid = p.get("turn_id")
        if tid not in ids:
            errors.append(f"{filename}: probe turn {tid} not in turns")
        else:
            role = next(t["role"] for t in turns if t["turn_id"] == tid)
            if role != "user":
                errors.append(f"{filename}: probe {tid} is not a user turn")
    ws = data.get("workstreams") or []
    n_ws = len(ws)
    if n_ws > 8:
        errors.append(f"{filename}: more than 8 workstreams ({n_ws})")
    if data.get("archetype") == "focused":
        if n_ws < 2:
            errors.append(f"{filename}: focused control should have at least 2 workstreams")
    elif n_ws < 3:
        errors.append(f"{filename}: expected at least 3 workstreams (found {n_ws})")
    return errors


def session_stats(data: dict) -> dict:
    turns = data["turns"]
    user_turns = [t for t in turns if t["role"] == "user"]
    n_ws = len(data["workstreams"])
    n_loops = sum(len(w.get("loops") or []) for w in data["workstreams"])
    n_domains = len(data.get("domains_present") or [])
    n_probes = len(data.get("probe_candidates") or [])
    n_abrupt = len(data.get("abrupt_domain_switches") or [])
    return {
        "session_id": data["session_id"],
        "archetype": data["archetype"],
        "interleaving": data["interleaving"],
        "turns": len(turns),
        "user_turns": len(user_turns),
        "workstreams": n_ws,
        "open_loops": n_loops,
        "domains": n_domains,
        "abrupt_switches": n_abrupt,
        "probe_candidates": n_probes,
        "label_status": data["label_status"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect interleaved pilot corpus (no models).")
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=CORPUS_DIR,
        help="Directory containing index.json and session files",
    )
    args = parser.parse_args(argv)

    index_path = args.corpus_dir / "index.json"
    if not index_path.is_file():
        print(f"missing {index_path}")
        return 1
    index = _load_json(index_path)
    print(f"corpus_id={index.get('corpus_id')} label_status={index.get('label_status')}")
    print(f"contextflow_run={index.get('contextflow_run')} (must stay false for this gate)")
    print()

    errors: list[str] = []
    rows = []
    inter = Counter()
    for entry in index.get("sessions") or []:
        path = args.corpus_dir / entry["file"]
        if not path.is_file():
            errors.append(f"missing session file {path.name}")
            continue
        data = _load_json(path)
        errors.extend(validate_session(data, path.name))
        rows.append(session_stats(data))
        inter[data.get("interleaving")] += 1

    headers = [
        "id",
        "archetype",
        "interleave",
        "turns",
        "user",
        "tasks",
        "loops",
        "dom",
        "abrupt",
        "probes",
    ]
    print("  ".join(h.ljust(8) for h in headers))
    for r in rows:
        print(
            f"{r['session_id']:<8}  {r['archetype']:<28}  {r['interleaving']:<14}  "
            f"{r['turns']:<8}  {r['user_turns']:<8}  {r['workstreams']:<8}  "
            f"{r['open_loops']:<8}  {r['domains']:<8}  {r['abrupt_switches']:<8}  "
            f"{r['probe_candidates']:<8}"
        )

    print()
    print(f"sessions={len(rows)} interleaving_counts={dict(inter)}")
    print(
        "Pilot 0: unlabeled. No gold. No ContextFlow. "
        "S03/S04 are the required abrupt cross-domain sessions."
    )
    if errors:
        print()
        print("VALIDATION ERRORS:")
        for e in errors:
            print(f"  - {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
