"""
Executive "What-If" Counterfactual Simulation Engine (V1 — overall
business totals only; no dimension/category filtering yet).

Supports:
  - Single scenario (discount OR price change by a given percent)
  - Sensitivity sweep (no percent given -> profit impact across a
    default range of percentages, like a spreadsheet data table)
  - Combined scenario (discount change AND price change together,
    applied in sequence: discount first, then price on the
    resulting baseline)
  - Break-even discount (how far discount can rise before profit
    hits zero, solved algebraically from the discount-scenario model)

Two supported scenario types:
  - discount: assumes sales volume (quantity) is unchanged; only the
    average discount rate shifts, and that shift flows straight
    through to profit dollar-for-dollar. Ignores any demand response
    to discounting.
  - price: uses a fixed price elasticity of demand to estimate how
    quantity would respond to a price change, and assumes cost per
    unit stays constant. An optimistic/pessimistic elasticity range
    is also reported alongside the central estimate, to communicate
    uncertainty honestly.

Nothing here writes to the database — purely a read + in-memory
calculation.
"""

from app.db.query_executor import execute_sql

PRICE_ELASTICITY_OF_DEMAND = -1.5       # central estimate
PRICE_ELASTICITY_OPTIMISTIC = -1.0      # less demand loss per % price increase
PRICE_ELASTICITY_PESSIMISTIC = -2.0     # more demand loss per % price increase

SENSITIVITY_PERCENTS = [5, 10, 15, 20]

BASELINE_QUERY = """
SELECT
    SUM(sales) AS total_sales,
    SUM(profit) AS total_profit,
    SUM(quantity) AS total_quantity,
    AVG(discount) AS avg_discount
FROM sales_records
"""


def get_baseline() -> dict:
    rows = execute_sql(BASELINE_QUERY)
    row = rows[0]
    return {
        "sales": float(row["total_sales"]),
        "profit": float(row["total_profit"]),
        "quantity": float(row["total_quantity"]),
        "discount": float(row["avg_discount"]),
    }


def simulate_discount_scenario(baseline: dict, direction: str, percent: float) -> dict:
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
        "simulated_quantity": baseline["quantity"],
    }


def simulate_price_scenario(baseline: dict, direction: str, percent: float,
                             elasticity: float = PRICE_ELASTICITY_OF_DEMAND) -> dict:
    sign = -1 if direction == "decrease" else 1
    price_pct_change = sign * percent / 100

    baseline_unit_price = baseline["sales"] / baseline["quantity"] if baseline["quantity"] else 0
    baseline_cost = baseline["sales"] - baseline["profit"]
    unit_cost = baseline_cost / baseline["quantity"] if baseline["quantity"] else 0

    quantity_pct_change = elasticity * price_pct_change
    new_quantity = max(baseline["quantity"] * (1 + quantity_pct_change), 0.0)
    new_unit_price = baseline_unit_price * (1 + price_pct_change)

    simulated_sales = new_quantity * new_unit_price
    simulated_cost = new_quantity * unit_cost
    simulated_profit = simulated_sales - simulated_cost

    return {
        "scenario": f"{direction} price by {percent:.0f}%",
        "assumption": (
            f"Central estimate uses a price elasticity of demand of {PRICE_ELASTICITY_OF_DEMAND} "
            f"(a 1% price change shifts quantity sold by {PRICE_ELASTICITY_OF_DEMAND}%), and "
            "assumes cost per unit stays constant. Real elasticity varies by product and "
            "segment — this model uses one constant value across the whole business."
        ),
        "baseline_sales": baseline["sales"],
        "simulated_sales": simulated_sales,
        "baseline_profit": baseline["profit"],
        "simulated_profit": simulated_profit,
        "profit_change": simulated_profit - baseline["profit"],
        "simulated_quantity": new_quantity,
    }


def simulate_price_scenario_with_range(baseline: dict, direction: str, percent: float) -> dict:
    """Central estimate plus optimistic/pessimistic bounds from a range of elasticity values."""
    central = simulate_price_scenario(baseline, direction, percent, PRICE_ELASTICITY_OF_DEMAND)
    optimistic = simulate_price_scenario(baseline, direction, percent, PRICE_ELASTICITY_OPTIMISTIC)
    pessimistic = simulate_price_scenario(baseline, direction, percent, PRICE_ELASTICITY_PESSIMISTIC)

    central["profit_range_low"] = min(optimistic["simulated_profit"], pessimistic["simulated_profit"])
    central["profit_range_high"] = max(optimistic["simulated_profit"], pessimistic["simulated_profit"])
    return central


def run_sensitivity_sweep(scenario_type: str, direction: str) -> list[dict]:
    """No specific percent given — profit impact across a default range of percentages."""
    baseline = get_baseline()
    rows = []
    for percent in SENSITIVITY_PERCENTS:
        if scenario_type == "discount":
            sim = simulate_discount_scenario(baseline, direction, percent)
        else:
            sim = simulate_price_scenario(baseline, direction, percent)
        rows.append({
            "percent": percent,
            "simulated_profit": sim["simulated_profit"],
            "profit_change": sim["profit_change"],
        })
    return rows


def run_combined_scenario(discount_direction: str, discount_percent: float,
                           price_direction: str, price_percent: float) -> dict:
    """
    Applies the discount change first, then the price change on top of the
    resulting (post-discount) baseline. Order is a modeling choice — stated
    explicitly in the returned assumption text.
    """
    baseline = get_baseline()
    step1 = simulate_discount_scenario(baseline, discount_direction, discount_percent)

    intermediate_baseline = {
        "sales": step1["simulated_sales"],
        "profit": step1["simulated_profit"],
        "quantity": baseline["quantity"],
        "discount": step1["simulated_discount_pct"] / 100,
    }
    step2 = simulate_price_scenario(intermediate_baseline, price_direction, price_percent)

    return {
        "scenario": (
            f"{discount_direction} discount by {discount_percent:.0f}% "
            f"and {price_direction} price by {price_percent:.0f}%"
        ),
        "assumption": (
            "Combined scenario: the discount change is applied first (profit-only effect, "
            "volume unchanged), then the price change (with its elasticity-driven demand effect) "
            "is applied on top of that adjusted baseline."
        ),
        "baseline_sales": baseline["sales"],
        "simulated_sales": step2["simulated_sales"],
        "baseline_profit": baseline["profit"],
        "simulated_profit": step2["simulated_profit"],
        "profit_change": step2["simulated_profit"] - baseline["profit"],
    }


def compute_breakeven_discount() -> dict:
    """
    Solves (using the discount-scenario model) for the average discount
    rate at which total profit would hit exactly zero.
    """
    baseline = get_baseline()
    if baseline["sales"] == 0:
        raise ValueError("Cannot compute break-even discount: total sales is zero.")

    additional_discount_points = baseline["profit"] / baseline["sales"]
    breakeven_discount = max(baseline["discount"] + additional_discount_points, 0.0)

    return {
        "baseline_discount_pct": baseline["discount"] * 100,
        "breakeven_discount_pct": breakeven_discount * 100,
        "additional_discount_points_pct": additional_discount_points * 100,
        "baseline_profit": baseline["profit"],
        "assumption": (
            "Uses the same discount model as the discount scenario (volume unchanged, "
            "discount flows straight through to profit) to solve for the discount rate "
            "at which total profit would reach exactly zero."
        ),
    }