"""R3 catalog→import→revive harness — controlled scenarios, frozen gate."""

from eval.ten_workstream.catalog_revive import load_scenarios, run_all


def test_r3_scenarios_file_declares_control_philosophy():
    doc = load_scenarios()
    meta = doc["meta"]
    assert meta["kind"] == "controlled_catalog_import_revive"
    assert "natural human chat" in " ".join(meta["not"]).lower() or any(
        "natural" in x.lower() for x in meta["not"]
    )
    assert any("CLARIFY" in x or "clarify" in x.lower() for x in meta["control_philosophy"])
    ids = {s["id"] for s in doc["scenarios"]}
    assert "r3_selective_import_revive" in ids
    assert "r3_honest_clarify_overlap" in ids


def test_r3_catalog_revive_harness_all_pass():
    payload = run_all()
    assert payload["summary"]["all_pass"] is True
    assert payload["summary"]["wrong_act_total"] == 0
    by_id = {r["scenario_id"]: r for r in payload["scenarios"]}
    sel = by_id["r3_selective_import_revive"]
    assert sel["probe_pass_count"] == sel["probe_n"] == 3
    assert sel["import_ok"] is True
    assert sel["match_ok"] is True
    assert sel.get("match_query")
    assert set(sel["id_map"]) == {"A", "B", "E"}
    # Remap must not keep source ids as live task ids.
    assert "A" not in sel["id_map"].values()

    clar = by_id["r3_honest_clarify_overlap"]
    assert clar["pass"] is True
    assert clar["match_ok"] is True
    assert clar["probes"][0]["act_or_clarify"] == "CLARIFY"
    assert clar["probes"][0]["policy_match"] is True

    assert by_id["r3_catalog_last_n"]["pass"] is True
    assert by_id["r3_paused_until_bind"]["pass"] is True
