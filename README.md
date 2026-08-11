# FinSAGE — Smart Answer Generation Engine for Finance

FinSAGE is a conversational analytics assistant that lets users query structured sales/financial data using natural language instead of SQL. Built as part of an AI internship at Fujitsu Noida, on a project connected to Denso Ten.

Instead of writing SQL or navigating dashboards, users can ask questions like *"Which region is driving the most profit?"* or *"What if we reduce discounts by 10%?"* and get grounded, explainable answers — with the underlying query, data, and assumptions always visible on request.

---

## Why this project

Most NL-to-SQL demos stop at "convert English to SQL and run it." FinSAGE is built around a **reliability layer** on top of that core idea — the parts that separate a toy demo from something closer to a real analytics tool:

- Ambiguous questions get clarified instead of silently guessed at
- Business metric formulas (like profit margin) are locked, not re-invented by the LLM every time
- Unusual patterns in results are proactively flagged, not left for the user to spot
- "What if" business scenarios are modeled with explicit, stated assumptions
- Failed queries self-correct instead of surfacing raw errors
- Repeated questions are cached instead of re-querying the LLM every time

---

## Core Features

### Conversational NL → SQL
Natural language questions are converted to PostgreSQL `SELECT` queries by an LLM (Gemini), using the database schema as context. Only `SELECT` statements are ever allowed to run — a validation layer blocks anything else before execution.

### Ambiguity Handling & Multi-Turn Clarification
A hybrid rule-based + LLM detector flags vague questions ("what's our best category?") and asks a clarifying question with tappable options instead of guessing. Multi-turn context is preserved across a clarification round, with a bounded retry cap so the conversation always resolves to a final answer rather than looping.

### Explainability
Every answer has a "How?" button that reveals the exact SQL query that was run and the row count behind it — nothing is a black box.

### Semantic Metric Layer
Business KPI formulas (profit margin, discount rate, average order value, sales growth rate) are locked in a central registry and injected into the LLM's prompt, so the same metric is always calculated the same way — not re-guessed on every question.

### Proactive Anomaly & Insight Engine
After every query, results are automatically scanned for:
- Statistical outliers (Z-score based)
- Rows running at a loss (hard rule)
- Possible "profit leaks" (high discount + non-positive profit)

Flagged insights appear as an alert banner under the answer — no user action needed to spot them.

### What-If Counterfactual Simulation Engine
Users can ask prospective business questions and get a modeled answer, entirely deterministically (no LLM call involved):
- **Discount scenarios** — e.g. *"What if we reduce discounts by 10%?"*
- **Price scenarios** — with a fixed price-elasticity-of-demand model, reported alongside an optimistic/pessimistic range
- **Combined scenarios** — discount and price change together, applied in sequence
- **Break-even analysis** — *"What's our break-even discount point?"* solves algebraically for the discount rate at which profit hits zero
- **Sensitivity sweep** — if no percentage is given, a table of outcomes across a default range (5%/10%/15%/20%) is shown instead of asking for more detail

Every simulated answer states its modeling assumptions explicitly.

### Agentic Self-Correction Loop
If generated SQL fails validation or execution, the exact error is fed back to the LLM (up to 2 retries) to self-correct — instead of showing the user a raw database error.

### Voice Input & Output
Questions can be asked by voice (Web Speech API `SpeechRecognition`); answers are read back in a concise, dashboard-style spoken summary (intro line + top result only — never a full list) rather than the full formatted text. Speaking only happens for turns that originated as voice input, including any clarification follow-ups in that same chain.

### Query Result Caching + Cost Stats
Exact-repeat questions are served from an in-memory cache instead of re-calling the LLM, cutting both latency and API cost. A JWT-protected `/admin/cache-stats` endpoint (surfaced in the Admin panel) reports hit rate, estimated Gemini calls saved, and estimated cost saved.

### Data Management
Full CRUD over the underlying sales dataset via a JWT-authenticated Admin panel — add, search, edit (with a Quick Edit + collapsible "More Fields" flow), and delete records — plus Search and Recent Records views.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python) |
| Database | PostgreSQL, via SQLAlchemy ORM |
| LLM | Google Gemini API (`gemini-3.5-flash-lite`, REST transport) |
| Auth | JWT (`python-jose`) |
| Visualization | Matplotlib (charts returned as base64 PNG) |
| Frontend | Vanilla HTML / CSS / JS |
| Voice | Web Speech API (`SpeechRecognition` + `SpeechSynthesis`) |

---

## Architecture

```
User question
     │
     ▼
[ What-If parser ]──match──► deterministic simulation engine (no LLM) ──► answer
     │ no match
     ▼
[ Cache lookup ] ──hit──► cached answer
     │ miss
     ▼
[ Ambiguity detector ] ──ambiguous──► clarification question + options
     │ clear
     ▼
[ NL → SQL (Gemini) ] ── uses locked metric formulas + schema context
     │
     ▼
[ Query validator ] ──rejected──► [ Self-correction loop: retry with error fed back to LLM ]
     │ valid
     ▼
[ Execute SQL against PostgreSQL ]
     │
     ▼
[ Anomaly detector ] ── flags outliers / losses / profit leaks
     │
     ▼
[ Answer generation (Gemini) ] + optional chart
     │
     ▼
Response → cached (if a fresh question) → returned to user (+ spoken aloud if voice-originated)
```

### Project Structure

```
app/
├── main.py
├── core/                    # config, JWT security
├── db/                      # models, session, schema loader, query executor
├── schemas/                 # Pydantic request/response schemas
├── llm/                     # nl_to_sql.py, response_gen.py
├── services/
│   ├── query_validator.py
│   ├── ambiguity_detector.py
│   ├── conversation_memory.py
│   ├── metrics_registry.py       # Semantic Metric Layer
│   ├── anomaly_detector.py       # Proactive Anomaly Engine
│   ├── whatif_parser.py          # What-If scenario parsing
│   ├── whatif_simulator.py       # What-If simulation math
│   ├── self_correction.py        # Agentic Self-Correction Loop
│   └── query_cache.py            # Caching + cost stats
├── viz/                     # chart_generator.py
├── api/routes/              # chat.py, records.py, auth.py
└── static/                  # frontend (HTML/CSS/JS)
```

---

## Dataset

[Kaggle Superstore Sales dataset](https://www.kaggle.com/datasets/vivek468/superstore-dataset-final) (9,994 rows) — order, customer, product, and financial data across four US regions.

---

## Getting Started

1. **Clone the repo and install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
2. **Set up PostgreSQL**, then load the dataset:
   - Download the [Superstore dataset](https://www.kaggle.com/datasets/vivek468/superstore-dataset-final) and place it at `data/Sample - Superstore.csv`
   - Run the loader script (creates tables via `init_db()` and bulk-inserts the CSV):
     ```bash
     python -m app.db.schema_loader
     ```
3. **Create a `.env` file** in the project root with:
   ```env
   DATABASE_URL=postgresql://<user>:<password>@localhost:5432/<db_name>
   GEMINI_API_KEY=<your Gemini API key>
   ADMIN_API_KEY=<a key of your choice, used for admin-level access>
   JWT_SECRET_KEY=<a long random secret string>
   JWT_ALGORITHM=HS256
   JWT_EXPIRY_MINUTES=60
   ```
4. **Run the server**
   ```bash
   uvicorn app.main:app --reload
   ```
5. Open `http://127.0.0.1:8000` in Chrome (voice input requires a Chromium-based browser).

---

## Known Limitations & Assumptions

- **What-If simulations** model overall business totals only — no per-category/region scenario support yet.
- **Price elasticity** uses a single constant value (-1.5) across the whole business; real elasticity varies by product/segment. An optimistic/pessimistic range is shown to communicate this uncertainty.
- **Discount scenarios** assume sales volume is unaffected by discount changes — only the profit-margin effect is modeled.
- **Query cache** is exact-text match, not semantic — differently-worded repeats of the same question won't hit the cache.
- **Voice input** requires a Chromium-based browser (Chrome/Edge); Web Speech API support elsewhere is limited.

## Future Improvements

- Dimension-specific What-If scenarios (e.g. "What if Furniture's discount drops 10%?")
- Migrating CLARIFY-avoidance from prompt instructions to Gemini's structured output (`response_schema` / JSON mode) for more reliable enforcement
- Semantic (embedding-based) query caching instead of exact-text match
- Streaming responses for perceived latency improvement

---

## Author

Jiya Lamba — B.Tech CSE, GTB Fourth Centenary Engineering College (GGSIPU) — AI Intern, Fujitsu Noida