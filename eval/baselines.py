from app.config import SETTINGS
from app.engine import Engine
from eval.scenarios import registry_for, scripted_llm


def run_contextflow(scn, mode="split"):
    """Run split or merged ContextFlow over a scenario; return probe rows."""
    reg = registry_for(scn)
    llm = scripted_llm(scn)
    eng = Engine(llm, reg, SETTINGS, mode=mode)
    rows = []
    probe_turn = scn.turns[-1][1]
    for (msg, turn, gold) in scn.turns:
        res = eng.handle_turn(msg, turn)
        is_probe = (turn == probe_turn)
        rows.append({
            "scenario_id": scn.scenario_id, "system": f"contextflow_{mode}",
            "open_count": scn.open_count, "underspec": scn.underspec,
            "interference": scn.interference, "turn": turn, "is_probe": is_probe,
            "transition": res.transition.value,
            "routed_task": res.task_id, "gold_task": gold,
            "gating_quantity": res.decision.gating_quantity,
            "decision_tokens": res.package.decision_tokens if res.package else 0,
            "answer_tokens": res.package.answer_tokens if res.package else 0,
        })
    return rows


SYSTEMS = {
    "contextflow_split": lambda s: run_contextflow(s, "split"),
    "contextflow_merged": lambda s: run_contextflow(s, "merged"),
}
