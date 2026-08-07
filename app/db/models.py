from sqlalchemy import Column, Integer, String, Float, Date
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class SalesRecord(Base):
    __tablename__ = "sales_records"

    row_id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String)
    order_date = Column(Date)
    ship_date = Column(Date)
    ship_mode = Column(String)
    customer_id = Column(String)
    customer_name = Column(String)
    segment = Column(String)
    country = Column(String)
    city = Column(String)
    state = Column(String)
    postal_code = Column(Integer)
    region = Column(String)
    product_id = Column(String)
    category = Column(String)
    sub_category = Column(String)
    product_name = Column(String)
    sales = Column(Float)
    quantity = Column(Integer)
    discount = Column(Float)
    profit = Column(Float)