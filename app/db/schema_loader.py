import pandas as pd
from sqlalchemy import text
from app.db.session import SessionLocal, init_db, engine
from app.db.models import SalesRecord

def load_csv_to_db(csv_path="data/Sample - Superstore.csv"):
    print("Initializing DB...")
    init_db()
    print("DB initialized. Reading CSV...")
    df = pd.read_csv(csv_path, encoding="latin1")
    print(f"CSV loaded: {len(df)} rows")

    # Clean column names to match model fields
    df.columns = [c.strip().lower().replace(" ", "_").replace("-", "_") for c in df.columns]

    # Convert date columns
    df["order_date"] = pd.to_datetime(df["order_date"], format="%m/%d/%Y").dt.date
    df["ship_date"] = pd.to_datetime(df["ship_date"], format="%m/%d/%Y").dt.date

    print("Connecting to session...")
    session = SessionLocal()
    print("Deleting old records...")
    session.query(SalesRecord).delete()  # avoid duplicates on re-run
    print("Old records deleted, inserting new...")

    records = df.to_dict(orient="records")
    session.bulk_insert_mappings(SalesRecord, records)
    session.commit()

    # Sync the auto-increment sequence (only needed for PostgreSQL; harmless no-op on SQLite)
    try:
        with engine.connect() as conn:
            conn.execute(text(
                "SELECT setval('sales_records_row_id_seq', (SELECT MAX(row_id) FROM sales_records))"
            ))
            conn.commit()
    except Exception as e:
        print(f"Sequence sync skipped (likely SQLite or sequence not found): {e}")

    
    session.close()
    print(f"Loaded {len(records)} records into DB.")

if __name__ == "__main__":
    load_csv_to_db()


def get_schema_description():
    return """
    Table: sales_records
    Columns: row_id (int), order_id (str), order_date (date), ship_date (date),
    ship_mode (str), customer_id (str), customer_name (str), segment (str),
    country (str), city (str), state (str), postal_code (int), region (str),
    product_id (str), category (str), sub_category (str), product_name (str),
    sales (float), quantity (int), discount (float), profit (float)
    """