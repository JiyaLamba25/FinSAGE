"""
Executive "What-If" Counterfactual Simulation Engine (V1 — overall
business totals only; no dimension/category filtering yet).

Two supported scenario types:
  - discount: assumes sales volume (quantity) is unchanged; only the
    average discount rate shifts, and that shift flows straight
    through to profit margin dollar-for-dollar. Ignores any demand
    response to discounting.
  - price: uses a fixed price elasticity of demand to estimate how
    quantity would respond to a price change, and assumes cost per
    unit stays constant. Real elasticity varies by product/segment;
    this model uses one constant value across the whole business.

Both scenarios pull CURRENT totals from the database as the
baseline, then apply the relevant formula. Nothing here writes to
the database — purely a read + in-memory calculation.
"""

from app.db.query_executor import execute_sql

PRICE_ELASTICITY_OF_DEMAND = -1.5  # % change in quantity per 1% change in price

BASELINE_QUERY = """
SELECT
    SUM(sales) AS total_sales,
    SUM(profit) AS total_profit,
    SUM(quantity) AS total_quantity,
    AVG(discount) AS avg_discount
FROM sales_records
"""


def _get_baseline() -> dict:
    rows = execute_sql(BASELINE_QUERY)
    row = rows[0]
    return {
        "sales": float(row["total_sales"]),
        "profit": float(row["total_profit"]),
        "quantity": float(row["total_quantity"]),
        "discount": float(row["avg_discount"]),
    }


def _simulate_discount_scenario(baseline: dict, direction: str, percent: float) -> dict:
    sign = -1 if direction == "decrease" else 1
    new_discount = baseline["discount"] * (1 + sign * percent / 100)
    new_discount = max(new_discount, 0.0)

    delta_discount = baseline["discount"] - new_discount
    simulated_profit = baseline["profit"] + delta_discount * baseline["sales"]
    simulated_sales = baseline["sales"]  # unchanged under this model

    return {
        "scenario": f"{direction} average discount by {percent:.0f}%",
        "assumption": (
            "Assumes sales volume stays the same and every percentage point of discount "
            "change flows straight through to profit. Demand response to discounting is not modeled."
        ),
        "baseline_discount_pct": baseline["discount"] * 100,
        "simulated_discount_pct": new_discount * 100,
        "baseline_sales": baseline["sales"],
        "simulated_sales": simulated_sales,
        "baseline_profit": baseline["profit"],
        "simulated_profit": simulated_profit,
        "profit_change": simulated_profit - baseline["profit"],
    }


def _simulate_price_scenario(baseline: dict, direction: str, percent: float) -> dict:
    sign = -1 if direction == "decrease" else 1
    price_pct_change = sign * percent / 100

    baseline_unit_price = baseline["sales"] / baseline["quantity"] if baseline["quantity"] else 0
    baseline_cost = baseline["sales"] - baseline["profit"]
    unit_cost = baseline_cost / baseline["quantity"] if baseline["quantity"] else 0

    quantity_pct_change = PRICE_ELASTICITY_OF_DEMAND * price_pct_change
    new_quantity = max(baseline["quantity"] * (1 + quantity_pct_change), 0.0)
    new_unit_price = baseline_unit_price * (1 + price_pct_change)

    simulated_sales = new_quantity * new_unit_price
    simulated_cost = new_quantity * unit_cost
    simulated_profit = simulated_sales - simulated_cost

    return {
        "scenario": f"{direction} price by {percent:.0f}%",
        "assumption": (
            f"Uses a fixed price elasticity of demand of {PRICE_ELASTICITY_OF_DEMAND} "
            f"(a 1% price change shifts quantity sold by {PRICE_ELASTICITY_OF_DEMAND}%), and "
            "assumes cost per unit stays constant. Real elasticity varies by product and "
            "segment — this model uses one constant value across the whole business."
        ),
        "baseline_sales": baseline["sales"],
        "simulated_sales": simulated_sales,
        "baseline_profit": baseline["profit"],
        "simulated_profit": simulated_profit,
        "profit_change": simulated_profit - baseline["profit"],
    }


def run_whatif_simulation(scenario_type: str, direction: str, percent: float) -> dict:
    baseline = _get_baseline()
    if scenario_type == "discount":
        return _simulate_discount_scenario(baseline, direction, percent)
    elif scenario_type == "price":
        return _simulate_price_scenario(baseline, direction, percent)
    raise ValueError(f"Unknown what-if scenario type: {scenario_type}")