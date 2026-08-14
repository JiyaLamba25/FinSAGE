import matplotlib
matplotlib.use("Agg")  # server ke liye zaroori, GUI nahi chahiye
import matplotlib.pyplot as plt
import io
import base64
from decimal import Decimal

CHART_KEYWORDS = ["chart", "graph", "plot", "visualize", "visualise", "bar chart", "pie chart", "line chart"]
TIME_KEYWORDS = ["date", "year", "month", "quarter", "week", "period"]
MIN_ROWS_FOR_AUTO_CHART = 2


def _is_numeric(value) -> bool:
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


def _is_id_like(key: str) -> bool:
    k = key.lower()
    return k.endswith("_id") or k == "id"


def _pick_label_and_value_columns(results: list):
    """
    Generated SQL always follows a `SELECT <dimension>, AGG(<metric>) ...
    GROUP BY <dimension>` shape — so the FIRST column is always the
    dimension/label, regardless of whether it happens to be numeric
    (e.g. discount_rate, year). The value column is the first numeric
    column found after that. This is more robust than guessing purely
    from data types, which breaks when the dimension itself is numeric.
    """
    if not results:
        return None, None

    keys = list(results[0].keys())
    candidate_keys = [k for k in keys if not _is_id_like(k)] or keys
    if len(candidate_keys) < 2:
        return None, None

    label_col = candidate_keys[0]
    value_col = None
    for k in candidate_keys[1:]:
        if _is_numeric(results[0][k]):
            value_col = k
            break

    if value_col is None:
        return None, None

    return label_col, value_col


def wants_visualization(question: str, results: list = None) -> bool:
    # Explicit request always wins.
    if any(kw in question.lower() for kw in CHART_KEYWORDS):
        return True

    # Otherwise, auto-decide from the shape of the results: need enough rows
    # and both a label column and a numeric value column.
    if results and len(results) >= MIN_ROWS_FOR_AUTO_CHART:
        label_col, value_col = _pick_label_and_value_columns(results)
        if label_col and value_col:
            return True

    return False


def detect_chart_type(question: str, results: list = None) -> str:
    q = question.lower()

    # Agar user ne explicitly bataya hai, wahi use karo
    if "pie" in q:
        return "pie"
    elif "line" in q:
        return "line"
    elif "bar" in q:
        return "bar"

    # Nahi bataya to data dekh ke decide karo
    if results and len(results) > 0:
        label_col, _ = _pick_label_and_value_columns(results)

        # Time/trend column ho to line chart better hai (trend dikhane ke liye)
        if label_col and any(tk in label_col.lower() for tk in TIME_KEYWORDS):
            return "line"

        # Kam categories (<=6) aur ek hi numeric value ho to pie chart theek lagta hai
        if len(results) <= 6:
            return "pie"

    # Default: bar chart (zyada categories/general comparison ke liye best)
    return "bar"


def generate_chart(results: list, chart_type: str = "bar") -> str:
    if not results:
        return None

    label_col, value_col = _pick_label_and_value_columns(results)
    if not label_col or not value_col:
        return None

    labels = [str(row[label_col]) for row in results]
    values = [float(row[value_col]) if isinstance(row[value_col], Decimal) else row[value_col] for row in results]

    fig, ax = plt.subplots(figsize=(8, 5))

    if chart_type == "pie":
        ax.pie(values, labels=labels, autopct="%1.1f%%")
    elif chart_type == "line":
        ax.plot(labels, values, marker="o")
        ax.set_xlabel(label_col)
        ax.set_ylabel(value_col)
    else:
        ax.bar(labels, values)
        ax.set_xlabel(label_col)
        ax.set_ylabel(value_col)
        plt.xticks(rotation=45, ha="right")

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)

    return base64.b64encode(buf.read()).decode("utf-8")