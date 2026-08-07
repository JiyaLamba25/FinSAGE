"""
Lightweight parser that detects "what-if" scenario questions and
extracts the scenario type, direction, and percentage — without
involving the LLM at all (this is a deterministic, rule-based
pipeline separate from the normal NL-to-SQL flow).
"""

import re
from typing import Optional

WHATIF_TRIGGERS = ["what if", "what-if", "hypothetically", "if we"]
INCREASE_WORDS = ["increase", "raise", "hike", "bump", "boost"]
DECREASE_WORDS = ["reduce", "decrease", "lower", "cut", "drop"]


def parse_whatif_question(question: str) -> Optional[dict]:
    """
    Returns None if this isn't a what-if question at all.
    Otherwise returns a dict with keys: type ('discount'|'price'),
    direction ('increase'|'decrease'|None), percent (float|None).
    direction/percent being None means the question needs more detail.
    """
    q = question.lower()
    if not any(trigger in q for trigger in WHATIF_TRIGGERS):
        return None

    if "discount" in q:
        scenario_type = "discount"
    elif "price" in q:
        scenario_type = "price"
    else:
        return None

    direction = None
    if any(word in q for word in INCREASE_WORDS):
        direction = "increase"
    elif any(word in q for word in DECREASE_WORDS):
        direction = "decrease"

    percent_match = re.search(r'(\d+(?:\.\d+)?)\s*%', q)
    percent = float(percent_match.group(1)) if percent_match else None

    return {
        "type": scenario_type,
        "direction": direction,
        "percent": percent,
    }