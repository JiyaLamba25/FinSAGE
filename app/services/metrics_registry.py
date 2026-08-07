"""
Semantic Metric Layer.

This module locks down the exact SQL formula for each named business
metric (profit margin, discount rate, etc.) so the LLM never has to
guess — and can't silently invent a different formula — when a user
mentions one of these metrics.

To add a new metric: add one entry to METRIC_DEFINITIONS below.
No other file needs to change; nl_to_sql.py pulls the prompt block
from build_metric_prompt_block() automatically.
"""

from typing import Optional, TypedDict


class MetricDefinition(TypedDict):
    aliases: list[str]      # phrases a user might use to refer to this metric
    sql_expression: str     # authoritative SQL expression (aggregate-level)
    description: str        # human-readable description injected into the prompt


METRIC_DEFINITIONS: dict[str, MetricDefinition] = {
    "profit_margin": {
        "aliases": ["profit margin", "margin", "profitability ratio"],
        "sql_expression": "SUM(profit) / NULLIF(SUM(sales), 0)",
        "description": "Profit margin = total profit divided by total sales.",
    },
    "discount_rate": {
        "aliases": ["discount rate", "average discount", "discount percentage"],
        "sql_expression": "AVG(discount)",
        "description": "Discount rate = average of the discount column.",
    },
    "average_order_value": {
        "aliases": ["average order value", "aov"],
        "sql_expression": "SUM(sales) / NULLIF(COUNT(DISTINCT order_id), 0)",
        "description": "Average order value = total sales divided by the number of distinct orders.",
    },
    "sales_growth_rate": {
        "aliases": ["sales growth", "growth rate", "yoy growth", "year-over-year growth", "year over year growth"],
        "sql_expression": (
            "(SUM(CASE WHEN EXTRACT(YEAR FROM order_date) = <later_year> THEN sales ELSE 0 END) - "
            "SUM(CASE WHEN EXTRACT(YEAR FROM order_date) = <earlier_year> THEN sales ELSE 0 END)) / "
            "NULLIF(SUM(CASE WHEN EXTRACT(YEAR FROM order_date) = <earlier_year> THEN sales ELSE 0 END), 0)"
        ),
        "description": (
            "Sales growth rate between two years = (sales in the later year - sales in the earlier year) "
            "/ sales in the earlier year. <later_year> and <earlier_year> must be replaced with the actual "
            "years being compared in the final SQL — never leave them as literal placeholder text."
        ),
    },
}


def find_metric_by_alias(text: str) -> Optional[MetricDefinition]:
    """Return the first metric whose alias appears in the given text (case-insensitive), else None."""
    lowered = text.lower()
    for metric in METRIC_DEFINITIONS.values():
        for alias in metric["aliases"]:
            if alias in lowered:
                return metric
    return None


def build_metric_prompt_block() -> str:
    """Render all metric definitions as a prompt-injectable block of authoritative formulas."""
    lines = [
        "Locked business metric formulas — you MUST use these exact formulas whenever the "
        "user's question refers to one of these metrics (by name or a close synonym). "
        "Do NOT invent or guess your own formula for any of these:"
    ]
    for metric in METRIC_DEFINITIONS.values():
        lines.append(f"- {metric['description']} SQL: {metric['sql_expression']}")
    return "\n".join(lines)