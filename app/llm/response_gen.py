import google.generativeai as genai
from google.api_core.exceptions import TooManyRequests
from app.core.config import GEMINI_API_KEY

genai.configure(api_key=GEMINI_API_KEY, transport="rest")
model = genai.GenerativeModel("gemini-3.5-flash-lite")

def generate_answer(question: str, results: list) -> str:
    prompt = f"""You are a helpful financial data assistant. Convert the query results into a clear, natural-language answer for a non-technical business user.

User's question: "{question}"

Query results (raw data):
{results}

Rules:
- If the results contain multiple items/rows (e.g. a list of top products, categories, regions, or any ranked/grouped data), format the answer as a Markdown numbered list (1. 2. 3. ...) with one line per item stating its name and key value. Add one short introductory sentence before the list.
- If the result is a single value or a single direct comparison (e.g. "total sales", "average profit", "which category had highest discount"), give a direct 1-2 sentence answer — no list.
- Use actual numbers from the results (format currency with ₹ or $ appropriately, round to 2 decimals).
- Do not mention SQL, databases, or technical terms.
- If results are empty, say no matching data was found.

Answer:"""

    try:
        response = model.generate_content(prompt, request_options={"timeout": 15})
    except TooManyRequests:
        return "RATE_LIMITED"
    except Exception:
        return "RATE_LIMITED"

    return response.text.strip()