"""Frozen case cards for the MultiWOZ local replay.

Difficulty is classified from the target turn + history ONLY, before any
ContextFlow or Ollama output is interpreted.

DST frames are not used as memory or as gold.
"""

from __future__ import annotations

# Recency / Jaccard constants frozen before the run.
RECENCY_K = 8
JACCARD_M = 6

CASES: list[dict] = [
    {
        "id": "PMUL0079",
        "headline": True,
        "dialogue_id": "PMUL0079.json",
        "target_turn_id": 8,
        "difficulty": "MEANINGFUL",
        "phenomenon": "interrupt_return",
        "genuine_return": True,
        "intended_workstream": "hotel/guesthouse",
        "intended_note": (
            "User interrupts restaurant food-type to resume unnamed guesthouse "
            "(name + parking). History has cheap + phone, not Worth House."
        ),
        "selection_any": ["hotel", "guest", "guesthouse", "cheap", "north", "01223316074"],
        "selection_avoid_only": ["restaurant", "food", "expensive"],
        "answer_ok_any": ["01223316074", "cheap", "worth", "guest", "parking", "do not have", "don't have", "not given", "unknown", "wasn't given"],
        "answer_bad_any": ["saigon"],
        "held_out_must_not_require": ["Worth House"],
    },
    {
        "id": "MUL2423",
        "headline": True,
        "dialogue_id": "MUL2423.json",
        "target_turn_id": 12,
        "difficulty": "AMBIGUOUS",
        "phenomenon": "interrupt_return",
        "genuine_return": True,
        "intended_workstream": "attraction/theatre",
        "intended_note": (
            "Taxi started; user goes back to pin which theatre. No theatre name "
            "in history. CLARIFY / ask which theatre is legitimate. Panahar is distractor."
        ),
        "selection_any": ["theatre", "theater", "attraction", "taxi"],
        "selection_avoid_only": ["panahar", "indian", "halal"],
        "answer_ok_any": ["theatre", "theater", "centre", "center", "which", "clarify", "several", "not specified", "don't know which"],
        "answer_bad_any": ["adc theatre"],  # not in history; hallucination of future wizard list
        "held_out_must_not_require": ["Cambridge Arts"],
        "clarify_ok": True,
    },
    {
        "id": "MUL2053",
        "headline": True,
        "dialogue_id": "MUL2053.json",
        "target_turn_id": 14,
        "difficulty": "MEANINGFUL",
        "phenomenon": "constraint_copy",
        "genuine_return": False,
        "intended_workstream": "train day copied from hotel stay",
        "intended_note": (
            "Not a return-to-hotel Q&A. Target is train travel day = hotel Tuesday. "
            "Needs earlier hotel booking constraint."
        ),
        "selection_any": ["tuesday", "hotel", "train", "stay"],
        "selection_avoid_only": [],
        "answer_ok_any": ["tuesday", "tue"],
        "answer_bad_any": ["wednesday", "monday", "thursday", "friday", "saturday", "sunday"],
        "needed_in_context_any": ["tuesday"],
    },
    {
        "id": "MUL0088",
        "headline": True,
        "dialogue_id": "MUL0088.json",
        "target_turn_id": 10,
        "difficulty": "MEANINGFUL",
        "phenomenon": "interrupt_return",
        "genuine_return": True,
        "intended_workstream": "hotel (Hamilton Lodge offer)",
        "intended_note": (
            "User had named Cow Pizza Kitchen; wizard offered Hamilton Lodge. "
            "'Does it have internet?' should bind to the lodge, not the restaurant. "
            "Internet is not yet in history."
        ),
        "selection_any": ["hotel", "lodge", "hamilton", "lodging", "parking", "star"],
        "selection_avoid_only": ["cow pizza", "restaurant"],
        "answer_ok_any": ["hamilton", "lodge", "hotel", "don't have", "do not have", "not said", "unknown", "wasn't told", "internet"],
        "answer_bad_any": [],
        "held_out_must_not_require": ["yes, the Hamilton Lodge has internet"],
    },
    {
        "id": "PMUL2746",
        "headline": True,
        "dialogue_id": "PMUL2746.json",
        "target_turn_id": 10,
        "difficulty": "EASY",
        "phenomenon": "constraint_copy",
        "genuine_return": False,
        "intended_workstream": "attraction area copied from hotel (south)",
        "intended_note": (
            "Deictic copy of hotel area into attractions. South is in history. "
            "Recency window of 8 likely still contains the hotel. Not A-B-A return."
        ),
        "selection_any": ["south", "hotel", "aylesbray", "attraction"],
        "selection_avoid_only": [],
        "answer_ok_any": ["south"],
        "answer_bad_any": ["north", "east", "west centre", "center of town only"],
        "needed_in_context_any": ["south"],
    },
    {
        "id": "MUL0810",
        "headline": True,
        "dialogue_id": "MUL0810.json",
        "target_turn_id": 12,
        "difficulty": "EASY",
        "phenomenon": "explicit_named_recover",
        "genuine_return": True,
        "intended_workstream": "attraction (Cambridge Museum of Technology)",
        "intended_note": (
            "Genuine return after restaurant, but the target names the entity. "
            "Postcode is NOT in history (only in held-out wizard). Jaccard/full history "
            "should route; answering cb58wr (Pizza Hut) is wrong-context."
        ),
        "selection_any": ["museum", "technology", "attraction", "camboats"],
        "selection_avoid_only": ["pizza", "italian", "restaurant"],
        "answer_ok_any": ["museum", "technology", "don't have", "do not have", "not given", "unknown", "cb58ld"],
        "answer_bad_any": ["cb58wr", "01223323737", "pizza hut"],
        "held_out_must_not_require": ["cb58ld"],
    },
    {
        "id": "PMUL4186",
        "headline": False,
        "dialogue_id": "PMUL4186.json",
        "target_turn_id": 8,
        "difficulty": "EASY",
        "phenomenon": "correction",
        "genuine_return": True,
        "intended_workstream": "hotel (Cambridge Belfry)",
        "intended_note": (
            "Sanity case, not headline. Target names Belfry. Wizard previously "
            "gave Nando's postcode. Parking/postcode for Belfry not fully in history."
        ),
        "selection_any": ["belfry", "hotel", "parking"],
        "selection_avoid_only": ["nandos", "nando"],
        "answer_ok_any": ["belfry", "parking", "don't have", "do not have", "not given", "unknown", "cb236bw"],
        "answer_bad_any": ["cb17dy", "nandos", "nando"],
        "held_out_must_not_require": ["cb236bw"],
    },
]
