from datetime import datetime, timedelta

# session_id -> { last_question, last_sql, last_results, pending_original_question, clarification_answers, clarification_rounds, timestamp }
_conversation_store = {}

SESSION_TIMEOUT_MINUTES = 30
MAX_CLARIFICATION_ROUNDS = 2

def save_context(session_id: str, question: str, sql: str = None, results: list = None,
                  pending_original_question: str = None, clarification_answers: list = None,
                  clarification_rounds: int = 0):
    _conversation_store[session_id] = {
        "last_question": question,
        "last_sql": sql,
        "last_results": results,
        "pending_original_question": pending_original_question,
        "clarification_answers": clarification_answers or [],
        "clarification_rounds": clarification_rounds,
        "timestamp": datetime.now()
    }

def get_context(session_id: str):
    entry = _conversation_store.get(session_id)
    if not entry:
        return None
    if datetime.now() - entry["timestamp"] > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
        del _conversation_store[session_id]
        return None
    return entry

def clear_context(session_id: str):
    _conversation_store.pop(session_id, None)