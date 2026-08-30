"""Utterance-level MultiWOZ inspection. DST used only for auxiliary depth stats.

Does not call ContextFlow or any LLM.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "multiwoz" / "dialogues_001.json"
OUT = Path(__file__).resolve().parent / "inspect.json"

CLOSE = re.compile(
    r"\b(thank|thanks|goodbye|bye|that('s| is) all|that will be all|"
    r"have a (nice|great) day|nothing else|that is it)\b",
    re.I,
)
SEQUENTIAL = re.compile(
    r"\b(i (also|would also) (need|want|like)|i'?m also looking|"
    r"also (need|looking|could you|can you)|i would also like|"
    r"i also need a (train|taxi|hotel|restaurant|attraction)|"
    r"looking for a (train|taxi|hotel|restaurant|attraction) (too|as well))\b",
    re.I,
)
INTERRUPT = re.compile(
    r"\b(before we do that|before that|wait,? (before|actually)|hold on)\b",
    re.I,
)
EXPLICIT_RETURN = re.compile(
    r"\b(i forgot|forgot to ask|you mentioned( earlier)?|mentioned earlier|"
    r"go back to|back to the)\b",
    re.I,
)
CORRECTION = re.compile(
    r"\b(you didn'?t answer|you did not answer|that('s| is) not (what|the)|"
    r"no on the hotel|i (actually|really) need)\b",
    re.I,
)
COPY = re.compile(
    r"\b(the same as the hotel|same day as the hotel|same area as the hotel|"
    r"same as the hotel|same day as (the )?(hotel|stay)|"
    r"same part of town|same area as)\b",
    re.I,
)
DEICTIC = re.compile(
    r"\b(does it have|is that |the one you|that one|which (theatre|theater|one))\b",
    re.I,
)
TAXI_GLUE = re.compile(
    r"\b(taxi|cab).{0,40}(hotel|restaurant|theatre|theater|attraction|museum|"
    r"guest ?house)\b|\b(from the|to the) (hotel|restaurant|guest ?house|museum)\b",
    re.I,
)


def primary_dst(turn: dict) -> str | None:
    for fr in turn.get("frames") or []:
        st = fr.get("state") or {}
        intent = st.get("active_intent")
        if intent not in (None, "NONE", ""):
            return fr.get("service")
    return None


def classify_utterance(utt: str) -> str:
    if CLOSE.search(utt) and not EXPLICIT_RETURN.search(utt):
        return "unsuitable"
    if INTERRUPT.search(utt):
        return "interruption"
    if CORRECTION.search(utt):
        return "correction"
    if EXPLICIT_RETURN.search(utt):
        return "genuine_return"
    if COPY.search(utt):
        return "copy_from_prior"
    if SEQUENTIAL.search(utt):
        return "sequential"
    if TAXI_GLUE.search(utt) and re.search(r"\btaxi\b", utt, re.I):
        return "sequential"
    if DEICTIC.search(utt):
        return "deictic"
    return "unclassified"


def dst_user_seq(d: dict) -> list[tuple[int, str | None, str]]:
    rows = []
    for t in d["turns"]:
        if t["speaker"] != "USER":
            continue
        rows.append((int(t["turn_id"]), primary_dst(t), t["utterance"]))
    return rows


def dst_depth(seq: list[tuple[int, str | None, str]]) -> dict:
    domains = [s for _, s, _ in seq if s]
    distinct = sorted(set(domains))
    switches = 0
    prev = None
    for s in domains:
        if prev is not None and s != prev:
            switches += 1
        prev = s
    max_return = 0
    genuine_dst_returns = 0
    for i, svc in enumerate(domains):
        earlier = [j for j in range(i) if domains[j] == svc]
        if not earlier:
            continue
        last = earlier[-1]
        mid = domains[last + 1 : i]
        if any(x and x != svc for x in mid):
            genuine_dst_returns += 1
            gap = i - last
            if gap > max_return:
                max_return = gap
    return {
        "n_user_turns": len(seq),
        "n_distinct_dst_domains": len(distinct),
        "n_dst_switches": switches,
        "max_dst_return_gap_user_turns": max_return,
        "n_dst_aba_returns": genuine_dst_returns,
        "dst_domain_seq": domains,
    }


def main() -> None:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    class_counts = Counter()
    dst_switches = Counter()
    dst_domains = Counter()
    dst_returns = Counter()
    max_gaps = []
    flagged: list[dict] = []
    mul = 0
    for d in data:
        services = d.get("services") or []
        if len(services) >= 2:
            mul += 1
        seq = dst_user_seq(d)
        depth = dst_depth(seq)
        dst_domains[depth["n_distinct_dst_domains"]] += 1
        dst_switches[depth["n_dst_switches"]] += 1
        dst_returns[depth["n_dst_aba_returns"]] += 1
        max_gaps.append(depth["max_dst_return_gap_user_turns"])
        for tid, svc, utt in seq:
            lab = classify_utterance(utt)
            class_counts[lab] += 1
            if lab in {
                "interruption",
                "genuine_return",
                "correction",
                "copy_from_prior",
                "deictic",
            }:
                flagged.append({
                    "dialogue_id": d["dialogue_id"],
                    "turn_id": tid,
                    "label": lab,
                    "dst_service": svc,
                    "services": services,
                    "utt": utt.replace("\n", " ")[:240],
                    "dst_depth": depth,
                })

    payload = {
        "n_dialogues": len(data),
        "n_multi_service": mul,
        "utterance_class_counts": dict(class_counts),
        "flagged_n": len(flagged),
        "dst_distinct_domain_hist": dict(sorted(dst_domains.items())),
        "dst_switch_hist": dict(sorted(dst_switches.items())),
        "dst_aba_return_hist": dict(sorted(dst_returns.items())),
        "max_dst_return_gap_mean": (sum(max_gaps) / len(max_gaps) if max_gaps else 0),
        "max_dst_return_gap_max": max(max_gaps) if max_gaps else 0,
        "flagged": flagged,
        "note": (
            "Utterance classes are heuristic. DST histograms are auxiliary dataset "
            "structure, not ContextFlow gold, not manufactured returns."
        ),
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("dialogues", len(data), "multi-service", mul)
    print("utterance classes", dict(class_counts))
    print("flagged (return-like heuristics)", len(flagged))
    print("DST distinct-domain hist", dict(sorted(dst_domains.items())))
    print("DST switch hist", dict(sorted(dst_switches.items())))
    print("DST A-B-A count hist", dict(sorted(dst_returns.items())))
    print("max DST return gap mean/max", payload["max_dst_return_gap_mean"], payload["max_dst_return_gap_max"])
    print("wrote", OUT)
    by = Counter(x["label"] for x in flagged)
    print("flagged by label", dict(by))
    for lab in ("interruption", "genuine_return", "correction", "copy_from_prior", "deictic"):
        rows = [x for x in flagged if x["label"] == lab]
        print(f"\n--- {lab} n={len(rows)} ---")
        for x in rows[:12]:
            print(f"  {x['dialogue_id']} t{x['turn_id']} dst={x['dst_service']}")
            print(f"    {x['utt'][:180]}")


if __name__ == "__main__":
    main()
