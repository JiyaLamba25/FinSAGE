from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.llm.nl_to_sql import generate_sql
from app.db.query_executor import execute_sql
from app.llm.response_gen import generate_answer
from app.services.query_validator import validate_sql
from app.services.ambiguity_detector import is_ambiguous, get_clarification_message
from app.services.conversation_memory import save_context, get_context, MAX_CLARIFICATION_ROUNDS
from app.services.anomaly_detector import detect_anomalies
from app.services.whatif_parser import parse_whatif_question
from app.services.whatif_simulator import run_whatif_simulation
from app.viz.chart_generator import generate_chart, detect_chart_type, wants_visualization

router = APIRouter()

class QuestionRequest(BaseModel):
    question: str
    session_id: str

class ExplainRequest(BaseModel):
    session_id: str


def parse_clarification(sql: str) -> dict:
    content = sql.replace("CLARIFY:", "").strip()
    if "| OPTIONS:" in content:
        message, options_str = content.split("| OPTIONS:")
        options = [opt.strip() for opt in options_str.split(",") if opt.strip()]
    else:
        message = content
        options = []
    options.append("Other")
    return {"message": message.strip(), "options": options}


OVERRIDE_SIGNALS = ["instead", "actually", "never mind", "different question"]


def is_likely_clarification_answer(question: str) -> bool:
    word_count = len(question.strip().split())
    return word_count <= 6


def build_contextual_question(req: QuestionRequest):
    context = get_context(req.session_id)
    if not context:
        return req.question, None, [], 0

    is_override = any(sig in req.question.lower() for sig in OVERRIDE_SIGNALS)
    pending_original = context.get("pending_original_question")
    rounds = context.get("clarification_rounds", 0)

    if pending_original and not is_override and is_likely_clarification_answer(req.question):
        answers = context.get("clarification_answers", []) + [req.question]
        combined = pending_original + " " + " ".join(f"({a})" for a in answers)
        return combined, pending_original, answers, rounds

    reference_question = context.get("last_question")
    follow_up_indicators = ["that", "this", "it", "compare to", " vs ", "previous", "last time", "instead"]
    if any(word in req.question.lower() for word in follow_up_indicators) and reference_question and not pending_original:
        combined = (
            f"Context: the user previously asked '{reference_question}'. "
            f"Keep the same grouping/dimension (e.g. region, category, etc.) used in that previous question "
            f"unless the new question explicitly specifies a different one. "
            f"New follow-up question: {req.question}"
        )
        return combined, None, [], 0

    return req.question, None, [], 0


@router.post("/chat/query")
def chat_query(req: QuestionRequest):

    # --- What-If Counterfactual Simulation (deterministic, bypasses LLM entirely) ---
    whatif_scenario = parse_whatif_question(req.question)
    if whatif_scenario:
        if not whatif_scenario["direction"] or not whatif_scenario["percent"]:
            return {
                "question": req.question,
                "generated_sql": None,
                "results": None,
                "answer": "For a what-if scenario, please specify a percentage and a direction — "
                          "e.g. \"What if we reduce discounts by 10%?\" or \"What if we increase price by 15%?\"",
                "options": [],
                "chart": None,
                "needs_clarification": False,
                "anomalies": []
            }

        sim = run_whatif_simulation(whatif_scenario["type"], whatif_scenario["direction"], whatif_scenario["percent"])

        if whatif_scenario["type"] == "discount":
            answer = (
                f"**{sim['scenario'].capitalize()}** (simulated):\n\n"
                f"- Average discount: {sim['baseline_discount_pct']:.2f}% → {sim['simulated_discount_pct']:.2f}%\n"
                f"- Total sales: ${sim['baseline_sales']:,.2f} → ${sim['simulated_sales']:,.2f} (unchanged, per model assumption)\n"
                f"- Total profit: ${sim['baseline_profit']:,.2f} → ${sim['simulated_profit']:,.2f} "
                f"({'+' if sim['profit_change'] >= 0 else ''}{sim['profit_change']:,.2f})\n\n"
                f"*Assumption: {sim['assumption']}*"
            )
        else:
            answer = (
                f"**{sim['scenario'].capitalize()}** (simulated):\n\n"
                f"- Total sales: ${sim['baseline_sales']:,.2f} → ${sim['simulated_sales']:,.2f}\n"
                f"- Total profit: ${sim['baseline_profit']:,.2f} → ${sim['simulated_profit']:,.2f} "
                f"({'+' if sim['profit_change'] >= 0 else ''}{sim['profit_change']:,.2f})\n\n"
                f"*Assumption: {sim['assumption']}*"
            )

        whatif_anomalies = detect_anomalies([{"scenario": "Simulated", "profit": sim["simulated_profit"]}])

        return {
            "question": req.question,
            "generated_sql": None,
            "results": None,
            "answer": answer,
            "options": [],
            "chart": None,
            "needs_clarification": False,
            "anomalies": whatif_anomalies
        }
    # --- end What-If block ---

    effective_question, pending_original, clarification_answers, rounds = build_contextual_question(req)
    force_final = rounds >= MAX_CLARIFICATION_ROUNDS

    if not pending_original and is_ambiguous(effective_question) and not force_final:
        clarification = get_clarification_message(effective_question)
        save_context(req.session_id, effective_question,
                     pending_original_question=effective_question,
                     clarification_answers=[],
                     clarification_rounds=0)
        return {
            "question": req.question,
            "generated_sql": None,
            "results": None,
            "answer": clarification["message"],
            "options": clarification["options"],
            "chart": None,
            "needs_clarification": True,
            "anomalies": []
        }

    sql = generate_sql(effective_question, force_final_answer=force_final)

    if sql == "RATE_LIMITED":
        return {
            "question": req.question,
            "generated_sql": None,
            "results": None,
            "answer": "The system is receiving too many requests right now. Please wait a few seconds and try again.",
            "options": [],
            "chart": None,
            "needs_clarification": False,
            "anomalies": []
        }

    if force_final and sql.strip().startswith("CLARIFY:"):
        parsed_fallback = parse_clarification(sql)
        assumed_default = parsed_fallback["options"][0] if parsed_fallback["options"] else "the most common default"
        retry_question = f"{effective_question}. Final assumption to use for any missing detail: {assumed_default}."
        sql = generate_sql(retry_question, force_final_answer=True)

    if force_final and sql.strip().startswith("CLARIFY:"):
        save_context(req.session_id, effective_question,
                     pending_original_question=None, clarification_answers=[], clarification_rounds=0)
        return {
            "question": req.question,
            "generated_sql": None,
            "results": None,
            "answer": "I wasn't able to resolve this automatically — could you try rephrasing your question with a specific time period and metric?",
            "options": [],
            "chart": None,
            "needs_clarification": False,
            "anomalies": []
        }

    if sql.startswith("CLARIFY:") and not force_final:
        parsed = parse_clarification(sql)
        save_context(req.session_id, effective_question,
                     pending_original_question=pending_original or effective_question,
                     clarification_answers=clarification_answers,
                     clarification_rounds=rounds + 1)
        return {
            "question": req.question,
            "generated_sql": None,
            "results": None,
            "answer": parsed["message"],
            "options": parsed["options"],
            "chart": None,
            "needs_clarification": True,
            "anomalies": []
        }

    if sql == "INVALID_QUERY":
        raise HTTPException(status_code=400, detail="Could not generate a valid query for this question")

    is_valid, error_msg = validate_sql(sql)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Query rejected: {error_msg}")

    try:
        results = execute_sql(sql)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query execution failed: {str(e)}")

    answer = generate_answer(effective_question, results)
    if answer == "RATE_LIMITED":
        return {
            "question": req.question,
            "generated_sql": sql,
            "results": results,
            "answer": "The system is receiving too many requests right now. Please wait a few seconds and try again.",
            "options": [],
            "chart": None,
            "needs_clarification": False,
            "anomalies": []
        }

    chart_base64 = None
    if wants_visualization(effective_question):
        chart_type = detect_chart_type(effective_question, results)
        chart_base64 = generate_chart(results, chart_type)

    anomalies = detect_anomalies(results)

    save_context(req.session_id, effective_question, sql=sql, results=results,
                 pending_original_question=None, clarification_answers=[], clarification_rounds=0)

    return {
        "question": req.question,
        "generated_sql": sql,
        "results": results,
        "answer": answer,
        "options": [],
        "chart": chart_base64,
        "needs_clarification": False,
        "anomalies": anomalies
    }


@router.post("/chat/explain")
def explain_last_query(req: ExplainRequest):
    context = get_context(req.session_id)
    if not context or not context.get("last_sql"):
        raise HTTPException(status_code=400, detail="No previous query available to explain.")

    sql = context["last_sql"]
    results = context.get("last_results") or []

    return {
        "explanation": f"This was calculated using: {sql}",
        "sql": sql,
        "row_count": len(results)
    }