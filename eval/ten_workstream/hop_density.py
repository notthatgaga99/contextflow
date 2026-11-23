"""Report per-workstream hop density and revive gaps for ten_workstream fixtures.

Learning / research utility. Does not change routing.
  python -m eval.ten_workstream.hop_density
  python -m eval.ten_workstream.hop_density --fixture eval/ten_workstream/fixture.json
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def analyze(fixture_path: Path) -> dict:
    fx = json.loads(fixture_path.read_text(encoding="utf-8"))
    turns = fx.get("turns") or []
    ws_meta = {w["id"]: w for w in (fx.get("workstreams") or [])}

    by_ws: dict[str, list[int]] = defaultdict(list)
    for t in turns:
        by_ws[str(t["ws"])].append(int(t["turn"]))

    rows = []
    for wid in sorted(by_ws.keys()):
        ts = sorted(by_ws[wid])
        gaps = [ts[i] - ts[i - 1] for i in range(1, len(ts))]
        # Revive-like: return after intervening turns from other workstreams
        max_gap = max(gaps) if gaps else 0
        meta = ws_meta.get(wid) or {}
        rows.append({
            "workstream": wid,
            "title": meta.get("title") or meta.get("goal") or "",
            "turns": len(ts),
            "first_turn": ts[0],
            "last_turn": ts[-1],
            "span": ts[-1] - ts[0] + 1,
            "max_gap_between_own_turns": max_gap,
            "target_turns": 20,
            "turns_shortfall": max(0, 20 - len(ts)),
        })

    return {
        "fixture": str(fixture_path.relative_to(ROOT)) if fixture_path.is_relative_to(ROOT) else str(fixture_path),
        "workstream_count": len(by_ws),
        "total_turns": len(turns),
        "avg_turns_per_ws": round(len(turns) / max(1, len(by_ws)), 2),
        "goal": "10 workstreams x >=20 interleaved turns + revive probes",
        "per_workstream": rows,
        "total_shortfall_to_20_each": sum(r["turns_shortfall"] for r in rows),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--fixture",
        type=Path,
        default=ROOT / "eval" / "ten_workstream" / "fixture.json",
    )
    ap.add_argument("--json", action="store_true", help="Print JSON only")
    args = ap.parse_args()
    report = analyze(args.fixture)
    if args.json:
        print(json.dumps(report, indent=2))
        return
    print(f"fixture: {report['fixture']}")
    print(
        f"workstreams={report['workstream_count']}  total_turns={report['total_turns']}  "
        f"avg/ws={report['avg_turns_per_ws']}"
    )
    print(f"goal: {report['goal']}")
    print(f"turns still needed to hit 20 each: {report['total_shortfall_to_20_each']}")
    print()
    print(f"{'ws':<4} {'turns':>5} {'short':>5} {'span':>5} {'max_gap':>7}  title")
    for r in report["per_workstream"]:
        print(
            f"{r['workstream']:<4} {r['turns']:>5} {r['turns_shortfall']:>5} "
            f"{r['span']:>5} {r['max_gap_between_own_turns']:>7}  {r['title'][:40]}"
        )


if __name__ == "__main__":
    main()
