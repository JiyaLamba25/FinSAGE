FORBIDDEN_KEYWORDS = [
    "insert", "update", "delete", "drop", "alter",
    "truncate", "create", "grant", "revoke", "attach",
    "detach", "pragma"
]

def validate_sql(sql: str) -> tuple[bool, str]:
    sql_lower = sql.lower().strip()

    if not sql_lower.startswith("select"):
        return False, "Only SELECT queries are allowed."

    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in sql_lower:
            return False, f"Query contains a forbidden operation: '{keyword}'"

    # Block multiple statements (stacked queries)
    cleaned = sql.strip().rstrip(";")
    if ";" in cleaned:
        return False, "Multiple statements are not allowed."

    if len(sql_lower) < 10:
        return False, "Generated query is too short to be valid."

    return True, ""