import google.generativeai as genai
from app.core.config import GEMINI_API_KEY
from app.db.schema_loader import get_schema_description
from app.services.metrics_registry import build_metric_prompt_block
from google.api_core.exceptions import TooManyRequests

genai.configure(api_key=GEMINI_API_KEY, transport="rest")
model = genai.GenerativeModel("gemini-3.5-flash-lite")

def generate_sql(question: str, force_final_answer: bool = False) -> str:
    schema = get_schema_description()
    metric_block = build_metric_prompt_block()

    force_instruction = ""
    if force_final_answer:
        force_instruction = (
            "\nCRITICAL OVERRIDE: This is the FINAL attempt for this question. You are STRICTLY FORBIDDEN "
            "from responding with CLARIFY or asking any question, under any circumstance. You MUST return a "
            "valid SQL SELECT query. If any detail is still unclear, silently pick the single most sensible "
            "default (e.g. all available years, monthly granularity, SUM aggregation, top 5 as default limit) "
            "and generate the query directly — do not explain the assumption, output ONLY the SQL."
        )

    prompt = f"""You are a SQL expert. Convert the user's natural language question into a single valid SQLite SELECT query.

Database schema:
{schema}

{metric_block}

Rules:
- Only generate SELECT queries. Never generate INSERT, UPDATE, DELETE, DROP, or ALTER.
- Use exact column and table names from the schema.
- This is a PostgreSQL database — use PostgreSQL date/time syntax only. Do NOT use SQLite functions like strftime(). For extracting year use EXTRACT(YEAR FROM order_date), for year-month grouping use TO_CHAR(order_date, 'YYYY-MM'), and for "current/most recent year" use (SELECT MAX(EXTRACT(YEAR FROM order_date)) FROM sales_records) instead of NOW() or CURRENT_DATE, since the dataset does not contain present-day data.
- If a metric mentioned above (in "Locked business metric formulas") appears in the question, use its exact formula — do not ask for clarification about which formula to use for it.
- If a metric is mentioned but is NOT in the locked list above, and the aggregation type isn't specified (e.g. "profit" without saying total or average), default to SUM/total — do not ask for clarification on this either.
- If the question uses a relative time reference like "this year", "current year", "today", "latest", or "recent", do NOT ask for clarification on the year — instead use the most recent year present in the order_date column of the data.
- If the question is genuinely ambiguous in a way NOT covered above (e.g. unclear grouping/comparison basis, or unclear specific years to compare when no relative term like "this year" is used), respond with exactly: CLARIFY: <a short clarifying question> | OPTIONS: option1, option2, option3
- Otherwise, return ONLY the raw SQL query. No explanation, no markdown, no code fences.
- If the question cannot be answered with this schema at all, return: INVALID_QUERY{force_instruction}

User question: "{question}"

Response:"""

    try:
        response = model.generate_content(
            prompt,
            request_options={"timeout": 15}  # hard cap — fail fast instead of long internal retries
        )
    except TooManyRequests:
        return "RATE_LIMITED"
    except Exception:
        return "RATE_LIMITED"  # covers timeout/DeadlineExceeded from the request_options above too
    result = response.text.strip()
    result = result.replace("```sql", "").replace("```", "").strip()
    return result