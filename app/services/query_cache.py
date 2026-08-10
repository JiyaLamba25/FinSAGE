"""
Query Result Cache + Cost/Performance Stats.

Caches complete, successful chat answers keyed by the normalized
question text, so an exact repeat question skips the LLM entirely.
Only applied to "fresh" standalone questions (no pending
clarification, no follow-up context merging) — see the is_fresh
check in chat.py.

Also tracks basic usage stats (hits/misses, estimated Gemini calls
and cost saved) so the effect of caching is measurable, not just
assumed — this is what gets surfaced as a resume-worthy metric.
"""

import time
from typing import Optional

CACHE_TTL_SECONDS = 30 * 60  # matches conversation_memory's SESSION_TIMEOUT_MINUTES
MAX_CACHE_ENTRIES = 200
ESTIMATED_CALLS_SAVED_PER_HIT = 2       # SQL-generation + answer-generation calls skipped
ESTIMATED_COST_PER_CALL_USD = 0.0005    # rough placeholder for gemini-3.5-flash-lite pricing

_cache: dict = {}   # normalized_question -> {"response": dict, "timestamp": float}
_stats = {
    "total_lookups": 0,
    "cache_hits": 0,
}


def normalize_question(question: str) -> str:
    return " ".join(question.strip().lower().split())


def get_cached(question: str) -> Optional[dict]:
    key = normalize_question(question)
    _stats["total_lookups"] += 1

    entry = _cache.get(key)
    if not entry:
        return None
    if time.time() - entry["timestamp"] > CACHE_TTL_SECONDS:
        del _cache[key]
        return None

    _stats["cache_hits"] += 1
    return entry["response"]


def set_cached(question: str, response: dict) -> None:
    key = normalize_question(question)
    if len(_cache) >= MAX_CACHE_ENTRIES and key not in _cache:
        oldest_key = min(_cache, key=lambda k: _cache[k]["timestamp"])
        del _cache[oldest_key]
    _cache[key] = {"response": response, "timestamp": time.time()}


def invalidate_cache() -> None:
    """Call this whenever the underlying data changes (Admin add/edit/delete)."""
    _cache.clear()


def get_cache_stats() -> dict:
    hit_rate = (_stats["cache_hits"] / _stats["total_lookups"] * 100) if _stats["total_lookups"] else 0.0
    calls_saved = _stats["cache_hits"] * ESTIMATED_CALLS_SAVED_PER_HIT
    estimated_cost_saved = calls_saved * ESTIMATED_COST_PER_CALL_USD
    return {
        "total_lookups": _stats["total_lookups"],
        "cache_hits": _stats["cache_hits"],
        "hit_rate_pct": round(hit_rate, 1),
        "estimated_calls_saved": calls_saved,
        "estimated_cost_saved_usd": round(estimated_cost_saved, 4),
        "current_cache_size": len(_cache),
    }