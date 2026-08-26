def routing_accuracy(rows) -> float:
    probes = [r for r in rows if r["is_probe"]]
    if not probes:
        return 0.0
    return sum(1 for r in probes if r["routed_task"] == r["gold_task"]) / len(probes)


def wrong_action_rate(rows) -> float:
    acted = [r for r in rows if r["is_probe"] and r["transition"] != "CLARIFY"]
    if not acted:
        return 0.0
    return sum(1 for r in acted if r["routed_task"] != r["gold_task"]) / len(acted)


def mean_tokens(rows):
    probes = [r for r in rows if r["is_probe"]]
    if not probes:
        return (0.0, 0.0, 0.0)
    d = sum(r["decision_tokens"] for r in probes) / len(probes)
    a = sum(r["answer_tokens"] for r in probes) / len(probes)
    return (d, a, d + a)


def risk_coverage(rows, thresholds):
    """Sweep THETA on the stored gating_quantity of probe turns."""
    probes = [r for r in rows if r["is_probe"]]
    curve = []
    for th in thresholds:
        acted = [r for r in probes if r["gating_quantity"] >= th]
        cov = len(acted) / len(probes) if probes else 0.0
        risk = (sum(1 for r in acted if r["routed_task"] != r["gold_task"]) / len(acted)
                if acted else 0.0)
        curve.append({"theta": th, "coverage": cov, "risk": risk})
    return curve
