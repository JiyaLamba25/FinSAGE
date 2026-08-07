VAGUE_TERMS = ["best", "worst", "top performing", "good", "bad", "most successful", "worst performing"]
METRIC_TERMS = ["profit", "sales", "revenue", "quantity", "discount", "orders", "order count"]

def is_ambiguous(question: str) -> bool:
    q = question.lower()
    has_vague = any(term in q for term in VAGUE_TERMS)
    has_metric = any(term in q for term in METRIC_TERMS)
    return has_vague and not has_metric

def get_clarification_message(question: str) -> dict:
    return {
        "message": "Could you clarify what metric you'd like this based on?",
        "options": ["Profit", "Total Sales", "Number of Orders", "Other"]
    }