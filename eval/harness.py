import csv
import os

from eval.scenarios import build_scenarios
from eval.baselines import SYSTEMS
from eval import metrics


def run(seed: int = 7, per_cell: int = 30, out_dir: str = "eval/out"):
    os.makedirs(out_dir, exist_ok=True)
    scenarios = build_scenarios(seed, per_cell=per_cell)
    all_rows = []
    for name, fn in SYSTEMS.items():
        for scn in scenarios:
            all_rows.extend(fn(scn))

    csv_path = os.path.join(out_dir, "rows.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        w.writeheader()
        w.writerows(all_rows)

    print(f"scenarios: {len(scenarios)}  rows: {len(all_rows)}  -> {csv_path}\n")
    print(f"{'system':20} {'route_acc':>9} {'wrong_act':>9} {'dec_tok':>8} {'ans_tok':>8} {'tot_tok':>8}")
    for name in SYSTEMS:
        rows = [r for r in all_rows if r["system"] == name]
        d, a, t = metrics.mean_tokens(rows)
        print(f"{name:20} {metrics.routing_accuracy(rows):9.3f} "
              f"{metrics.wrong_action_rate(rows):9.3f} {d:8.1f} {a:8.1f} {t:8.1f}")

    # split-vs-merged go/no-go summary
    split = [r for r in all_rows if r["system"] == "contextflow_split"]
    merged = [r for r in all_rows if r["system"] == "contextflow_merged"]
    _, _, ts = metrics.mean_tokens(split)
    _, _, tm = metrics.mean_tokens(merged)
    print(f"\nGO/NO-GO: split total_tok={ts:.1f} vs merged total_tok={tm:.1f} "
          f"| split_route_acc={metrics.routing_accuracy(split):.3f} "
          f"merged_route_acc={metrics.routing_accuracy(merged):.3f}")
    return all_rows


if __name__ == "__main__":
    run(per_cell=10)
