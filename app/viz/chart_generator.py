import matplotlib
matplotlib.use("Agg")  # server ke liye zaroori, GUI nahi chahiye
import matplotlib.pyplot as plt
import io
import base64

def wants_visualization(question: str) -> bool:
    keywords = ["chart", "graph", "plot", "visualize", "visualise", "bar chart", "pie chart", "line chart"]
    return any(kw in question.lower() for kw in keywords)

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
        keys = list(results[0].keys())

        # Agar date/time column hai to line chart better hai (trend dikhane ke liye)
        if any("date" in k.lower() for k in keys):
            return "line"

        # Kam categories (<=6) aur ek hi numeric value ho to pie chart theek lagta hai (proportion dikhane ke liye)
        if len(results) <= 6:
            return "pie"

    # Default: bar chart (zyada categories/general comparison ke liye best)
    return "bar"

def generate_chart(results: list, chart_type: str = "bar") -> str:
    if not results:
        return None

    keys = list(results[0].keys())
    labels = [str(row[keys[0]]) for row in results]
    values = [row[keys[1]] for row in results]

    fig, ax = plt.subplots(figsize=(8, 5))

    if chart_type == "pie":
        ax.pie(values, labels=labels, autopct="%1.1f%%")
    elif chart_type == "line":
        ax.plot(labels, values, marker="o")
        ax.set_xlabel(keys[0])
        ax.set_ylabel(keys[1])
    else:
        ax.bar(labels, values)
        ax.set_xlabel(keys[0])
        ax.set_ylabel(keys[1])
        plt.xticks(rotation=45, ha="right")

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)

    return base64.b64encode(buf.read()).decode("utf-8")