"""
Agentic Self-Correction Loop.

Takes an already-generated SQL query and, if it's rejected by the
validator or fails at execution time, feeds the exact error back to
the LLM and asks it to fix its own SQL — instead of surfacing a raw
error straight to the user. Retries a bounded number of times
(MAX_SELF_CORRECTION_RETRIES) before giving up gracefully.

Correction retries always pass force_final_answer=True to nl_to_sql,
so the LLM can't respond with a CLARIFY question mid-correction — by
this point the original question has already been resolved to a
concrete SQL attempt; a correction retry should only ever return
fixed SQL.
"""

from app.llm.nl_to_sql import generate_sql
from app.services.query_validator import validate_sql
from app.db.query_executor import execute_sql

MAX_SELF_CORRECTION_RETRIES = 2


def execute_with_self_correction(question: str, initial_sql: str) -> dict:
    """
    Returns one of:
      {"status": "ok", "sql": <str>, "results": <list[dict]>, "attempts": <int>}
      {"status": "rate_limited"}
      {"status": "failed", "last_error": <str>}
    """
    sql = initial_sql
    last_error = None

    for attempt in range(MAX_SELF_CORRECTION_RETRIES + 1):
        is_valid, validation_error = validate_sql(sql)
        if not is_valid:
            last_error = f"Query rejected by validator: {validation_error}"
        else:
            try:
                results = execute_sql(sql)
                return {"status": "ok", "sql": sql, "results": results, "attempts": attempt + 1}
            except Exception as e:
                last_error = f"Query execution failed: {str(e)}"

        if attempt < MAX_SELF_CORRECTION_RETRIES:
            correction_prompt = (
                f"{question}\n\n"
                f"IMPORTANT: Your previous SQL attempt failed and must be corrected.\n"
                f"Previous SQL: {sql}\n"
                f"Error: {last_error}\n"
                f"Return ONLY the corrected SQL query that fixes this error. "
                f"No explanation, no markdown, no CLARIFY."
            )
            sql = generate_sql(correction_prompt, force_final_answer=True)
            if sql == "RATE_LIMITED":
                return {"status": "rate_limited"}

    return {"status": "failed", "last_error": last_error}