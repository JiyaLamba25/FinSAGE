"""
Lightweight parser that detects "what-if" scenario questions and
extracts scenario clauses (type, direction, percent) — without
involving the LLM at all (deterministic, rule-based, separate from
the normal NL-to-SQL flow).
"""

import re
from typing import Optional

WHATIF_TRIGGERS = ["what if", "what-if", "hypothetically", "if we"]
BREAKEVEN_TRIGGERS = [
    "break even", "break-even", "breakeven",
    "how much can we discount", "how much discount can we",
    "maximum discount", "max discount",
]
INCREASE_WORDS = ["increase", "raise", "hike", "bump", "boost"]
DECREASE_WORDS = ["reduce", "decrease", "lower", "cut", "drop"]

CLAUSE_SPLIT_RE = re.compile(r'\band\b|,')


def _parse_clause(clause: str) -> Optional[dict]:
    if "discount" in clause:
        scenario_type = "discount"
    elif "price" in clause:
        scenario_type = "price"
    else:
        return None

    direction = None
    if any(word in clause for word in INCREASE_WORDS):
        direction = "increase"
    elif any(word in clause for word in DECREASE_WORDS):
        direction = "decrease"

    percent_match = re.search(r'(\d+(?:\.\d+)?)\s*%', clause)
    percent = float(percent_match.group(1)) if percent_match else None

    return {"type": scenario_type, "direction": direction, "percent": percent}


def parse_whatif_question(question: str) -> Optional[dict]:
    """
    Returns None if this isn't a what-if/break-even question at all.
    Otherwise returns:
      {
        "is_breakeven": bool,
        "scenarios": [ {type, direction, percent}, ... ]  # one entry per clause
      }
    A scenario with percent=None means "no percent given" -> caller should
    run a sensitivity sweep instead of a single simulation.
    """
    q = question.lower()

    is_breakeven = any(trigger in q for trigger in BREAKEVEN_TRIGGERS)
    is_whatif = any(trigger in q for trigger in WHATIF_TRIGGERS)

    if not is_breakeven and not is_whatif:
        return None

    if is_breakeven:
        return {"is_breakeven": True, "scenarios": []}

    clauses = CLAUSE_SPLIT_RE.split(q)
    scenarios = [parsed for clause in clauses if (parsed := _parse_clause(clause))]

    if not scenarios:
        return None

    return {"is_breakeven": False, "scenarios": scenarios}