from pydantic import BaseModel
from datetime import date

class SalesRecordCreate(BaseModel):
    order_id: str
    order_date: date
    ship_date: date
    ship_mode: str
    customer_id: str
    customer_name: str
    segment: str
    country: str
    city: str
    state: str
    postal_code: int
    region: str
    product_id: str
    category: str
    sub_category: str
    product_name: str
    sales: float
    quantity: int
    discount: float
    profit: float

class SalesRecordUpdate(BaseModel):
    order_id: str | None = None
    order_date: date | None = None
    ship_date: date | None = None
    ship_mode: str | None = None
    customer_id: str | None = None
    customer_name: str | None = None
    segment: str | None = None
    country: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: int | None = None
    region: str | None = None
    product_id: str | None = None
    category: str | None = None
    sub_category: str | None = None
    product_name: str | None = None
    sales: float | None = None
    quantity: int | None = None
    discount: float | None = None
    profit: float | None = None