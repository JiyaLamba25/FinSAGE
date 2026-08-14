from fastapi import APIRouter, HTTPException, Depends
from app.core.security import verify_token
from pydantic import BaseModel
from app.llm.nl_to_sql import generate_sql
from app.db.query_executor import execute_sql
from app.llm.response_gen import generate_answer
from app.services.ambiguity_detector import is_ambiguous, get_clarification_message
from app.services.conversation_memory import save_context, get_context, MAX_CLARIFICATION_ROUNDS
from app.services.anomaly_detector import detect_anomalies
from app.services.self_correction import execute_with_self_correction
from app.services.query_cache import get_cached, set_cached, get_cache_stats
from app.services.whatif_parser import parse_whatif_question
from app.services.whatif_simulator import (
    get_baseline,
    simulate_discount_scenario,
    simulate_price_scenario_with_range,
    run_sensitivity_sweep,
    run_combined_scenario,
    compute_breakeven_discount,
)
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

COMPREHENSIVE_REQUEST_KEYWORDS = [
    "everything", "all information", "all metrics", "all details",
    "full picture", "overview", "summary of everything",
]


def is_likely_clarification_answer(question: str) -> bool:
    word_count = len(question.strip().split())
    return word_count <= 6


def is_comprehensive_request(text: str) -> bool:
    q = text.lower()
    return any(keyword in q for keyword in COMPREHENSIVE_REQUEST_KEYWORDS)


def build_contextual_question(req: QuestionRequest):
    context = get_context(req.session_id)
    if not context:
        return req.question, None, [], 0, False

    is_override = any(sig in req.question.lower() for sig in OVERRIDE_SIGNALS)
    pending_original = context.get("pending_original_question")
    rounds = context.get("clarification_rounds", 0)

    if pending_original and not is_override and is_likely_clarification_answer(req.question):
        answers = context.get("clarification_answers", []) + [req.question]
        combined = pending_original + " " + " ".join(f"({a})" for a in answers)
        comprehensive_override = is_comprehensive_request(req.question)
        return combined, pending_original, answers, rounds, comprehensive_override

    reference_question = context.get("last_question")
    follow_up_indicators = ["that", "this", "it", "compare to", " vs ", "previous", "last time", "instead"]
    if any(word in req.question.lower() for word in follow_up_indicators) and reference_question and not pending_original:
        combined = (
            f"Context: the user previously asked '{reference_question}'. "
            f"Keep the same grouping/dimension (e.g. region, category, etc.) used in that previous question "
            f"unless the new question explicitly specifies a different one. "
            f"New follow-up question: {req.question}"
        )
        return combined, None, [], 0, False

    return req.question, None, [], 0, False


@router.post("/chat/query")
def chat_query(req: QuestionRequest):


     
    # --- What-If Counterfactual Simulation (deterministic, bypasses LLM entirely) ---
    whatif_result = parse_whatif_question(req.question)
    if whatif_result:

        if whatif_result["is_breakeven"]:
            try:
                be = compute_breakeven_discount()
            except ValueError as e:
                return {
                    "question": req.question, "generated_sql": None, "results": None,
                    "answer": str(e), "options": [], "chart": None,
                    "needs_clarification": False, "anomalies": []
                }
            answer = (
                f"**Break-even discount point** (simulated):\n\n"
                f"- Current average discount: {be['baseline_discount_pct']:.2f}%\n"
                f"- Break-even average discount: {be['breakeven_discount_pct']:.2f}% "
                f"(about {be['additional_discount_points_pct']:.2f} more percentage points)\n"
                f"- Current total profit: ${be['baseline_profit']:,.2f}\n\n"
                f"*Assumption: {be['assumption']}*"
            )
            return {
                "question": req.question, "generated_sql": None, "results": None,
                "answer": answer, "options": [], "chart": None,
                "needs_clarification": False, "anomalies": []
            }

        scenarios = whatif_result["scenarios"]
        discount_sc = next((s for s in scenarios if s["type"] == "discount"), None)
        price_sc = next((s for s in scenarios if s["type"] == "price"), None)

        if discount_sc and price_sc:
            if not discount_sc["direction"] or not price_sc["direction"]:
                return {
                    "question": req.question, "generated_sql": None, "results": None,
                    "answer": "For a combined scenario, please specify a direction (increase/decrease) "
                              "for both the discount and the price change.",
                    "options": [], "chart": None, "needs_clarification": False, "anomalies": []
                }
            if not discount_sc["percent"] or not price_sc["percent"]:
                return {
                    "question": req.question, "generated_sql": None, "results": None,
                    "answer": "For a combined scenario, please specify a percentage for both changes — "
                              "e.g. \"What if we reduce discounts by 10% and increase price by 5%?\"",
                    "options": [], "chart": None, "needs_clarification": False, "anomalies": []
                }
            sim = run_combined_scenario(discount_sc["direction"], discount_sc["percent"],
                                         price_sc["direction"], price_sc["percent"])
            answer = (
                f"**{sim['scenario'].capitalize()}** (simulated):\n\n"
                f"- Total sales: ${sim['baseline_sales']:,.2f} → ${sim['simulated_sales']:,.2f}\n"
                f"- Total profit: ${sim['baseline_profit']:,.2f} → ${sim['simulated_profit']:,.2f} "
                f"({'+' if sim['profit_change'] >= 0 else ''}{sim['profit_change']:,.2f})\n\n"
                f"*Assumption: {sim['assumption']}*"
            )
            chart_data = [
                {"scenario": "Baseline", "profit": sim["baseline_profit"]},
                {"scenario": "Simulated", "profit": sim["simulated_profit"]},
            ]
            chart_base64 = generate_chart(chart_data, "bar")
            anomalies = detect_anomalies([{"scenario": "Simulated (combined)", "profit": sim["simulated_profit"]}])
            return {
                "question": req.question, "generated_sql": None, "results": None,
                "answer": answer, "options": [], "chart": chart_base64,
                "needs_clarification": False, "anomalies": anomalies
            }

        sc = scenarios[0]
        if not sc["direction"]:
            return {
                "question": req.question, "generated_sql": None, "results": None,
                "answer": "For a what-if scenario, please specify a direction — "
                          "e.g. \"What if we reduce discounts by 10%?\" or \"What if we increase price by 15%?\"",
                "options": [], "chart": None, "needs_clarification": False, "anomalies": []
            }

        if sc["percent"] is None:
            sweep = run_sensitivity_sweep(sc["type"], sc["direction"])
            baseline_for_display = get_baseline()
            baseline_profit_display = baseline_for_display["profit"]
            label = "Discount" if sc["type"] == "discount" else "Price"
            table_rows = "\n".join(
                f"| {row['percent']:.0f}% | ${row['simulated_profit']:,.2f} | "
                f"{'+' if row['profit_change'] >= 0 else ''}{row['profit_change']:,.2f} |"
                for row in sweep
            )
            answer = (
                f"No specific percentage given, so here's a sensitivity sweep for "
                f"**{sc['direction']} {label.lower()}** across a default range.\n\n"
                f"Current (baseline) profit: **${baseline_profit_display:,.2f}**\n\n"
                f"| {label} Change | Simulated Profit | Profit Change |\n"
                f"|---|---|---|\n"
                f"{table_rows}\n\n"
                f"*Ask with a specific percentage (e.g. \"by 10%\") for a single detailed scenario instead.*"
            )
            chart_data = [{"change": "Baseline", "profit": baseline_profit_display}] + [
                {"change": f"{row['percent']:.0f}%", "profit": row["simulated_profit"]} for row in sweep
            ]
            chart_base64 = generate_chart(chart_data, "bar")
            worst_row = min(sweep, key=lambda r: r["simulated_profit"])
            anomalies = detect_anomalies([{"scenario": f"Sensitivity worst-case ({worst_row['percent']:.0f}%)",
                                            "profit": worst_row["simulated_profit"]}])
            return {
                "question": req.question, "generated_sql": None, "results": None,
                "answer": answer, "options": [], "chart": chart_base64,
                "needs_clarification": False, "anomalies": anomalies
            }

        baseline = get_baseline()
        if sc["type"] == "discount":
            sim = simulate_discount_scenario(baseline, sc["direction"], sc["percent"])
            answer = (
                f"**{sim['scenario'].capitalize()}** (simulated):\n\n"
                f"- Average discount: {sim['baseline_discount_pct']:.2f}% → {sim['simulated_discount_pct']:.2f}%\n"
                f"- Total sales: ${sim['baseline_sales']:,.2f} → ${sim['simulated_sales']:,.2f} (unchanged, per model assumption)\n"
                f"- Total profit: ${sim['baseline_profit']:,.2f} → ${sim['simulated_profit']:,.2f} "
                f"({'+' if sim['profit_change'] >= 0 else ''}{sim['profit_change']:,.2f})\n\n"
                f"*Assumption: {sim['assumption']}*"
            )
        else:
            sim = simulate_price_scenario_with_range(baseline, sc["direction"], sc["percent"])
            answer = (
                f"**{sim['scenario'].capitalize()}** (simulated):\n\n"
                f"- Total sales: ${sim['baseline_sales']:,.2f} → ${sim['simulated_sales']:,.2f}\n"
                f"- Total profit: ${sim['baseline_profit']:,.2f} → ${sim['simulated_profit']:,.2f} "
                f"({'+' if sim['profit_change'] >= 0 else ''}{sim['profit_change']:,.2f})\n"
                f"- Range (depending on actual demand sensitivity): "
                f"${sim['profit_range_low']:,.2f} to ${sim['profit_range_high']:,.2f}\n\n"
                f"*Assumption: {sim['assumption']}*"
            )

        chart_data = [
            {"scenario": "Baseline", "profit": sim["baseline_profit"]},
            {"scenario": "Simulated", "profit": sim["simulated_profit"]},
        ]
        chart_base64 = generate_chart(chart_data, "bar")
        anomalies = detect_anomalies([{"scenario": "Simulated", "profit": sim["simulated_profit"]}])
        return {
            "question": req.question, "generated_sql": None, "results": None,
            "answer": answer, "options": [], "chart": chart_base64,
            "needs_clarification": False, "anomalies": anomalies
        }
    # --- end What-If block ---

    effective_question, pending_original, clarification_answers, rounds, comprehensive_override = build_contextual_question(req)
    force_final = rounds >= MAX_CLARIFICATION_ROUNDS or comprehensive_override

    # A "fresh" question: no pending clarification, and no follow-up context
    # was merged in. Only these get cached/looked-up — a clarification answer
    # or a follow-up depends on conversation state, not just its own text.
    is_fresh = pending_original is None and effective_question == req.question

    if is_fresh:
        cached_response = get_cached(req.question)
        if cached_response:
            save_context(req.session_id, effective_question,
                         sql=cached_response.get("generated_sql"),
                         results=cached_response.get("results"),
                         pending_original_question=None, clarification_answers=[], clarification_rounds=0)
            return cached_response

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

    sql = generate_sql(effective_question, force_final_answer=force_final, comprehensive=comprehensive_override)

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
        sql = generate_sql(retry_question, force_final_answer=True, comprehensive=comprehensive_override)

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

    correction_result = execute_with_self_correction(effective_question, sql)

    if correction_result["status"] == "rate_limited":
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

    if correction_result["status"] == "failed":
        return {
            "question": req.question,
            "generated_sql": None,
            "results": None,
            "answer": "I generated a query for this but couldn't get it to run successfully after a couple of "
                      "attempts — could you try rephrasing the question?",
            "options": [],
            "chart": None,
            "needs_clarification": False,
            "anomalies": []
        }

    sql = correction_result["sql"]
    results = correction_result["results"]

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
    if wants_visualization(effective_question, results):
        chart_type = detect_chart_type(effective_question, results)
        chart_base64 = generate_chart(results, chart_type)

    anomalies = detect_anomalies(results)

    save_context(req.session_id, effective_question, sql=sql, results=results,
                 pending_original_question=None, clarification_answers=[], clarification_rounds=0)

    response_payload = {
        "question": req.question,
        "generated_sql": sql,
        "results": results,
        "answer": answer,
        "options": [],
        "chart": chart_base64,
        "needs_clarification": False,
        "anomalies": anomalies
    }

    if is_fresh:
        set_cached(req.question, response_payload)

    return response_payload


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


@router.get("/admin/cache-stats", dependencies=[Depends(verify_token)])
def cache_stats():
    return get_cache_stats()