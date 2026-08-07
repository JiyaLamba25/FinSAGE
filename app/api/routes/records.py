from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.db.session import SessionLocal
from app.db.models import SalesRecord
from app.schemas.sales_record import SalesRecordCreate, SalesRecordUpdate
from app.core.security import verify_token

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/records", dependencies=[Depends(verify_token)])
def add_record(record: SalesRecordCreate, db: Session = Depends(get_db)):
    new_record = SalesRecord(**record.model_dump())
    db.add(new_record)
    db.commit()
    db.refresh(new_record)
    return new_record

@router.get("/records/recent")
def get_recent(limit: int = 5, db: Session = Depends(get_db)):
    return db.query(SalesRecord).order_by(desc(SalesRecord.row_id)).limit(limit).all()

@router.get("/records/search/{order_id}")
def search_by_order_id(order_id: str, db: Session = Depends(get_db)):
    records = db.query(SalesRecord).filter(SalesRecord.order_id == order_id).all()
    if not records:
        raise HTTPException(status_code=404, detail="No records found for this order ID")
    # user-friendly summary — taaki wo pick kar sake kaunsi row chahiye
    return [
        {
            "row_id": r.row_id,
            "product_name": r.product_name,
            "category": r.category,
            "sub_category": r.sub_category,
            "region": r.region,
            "quantity": r.quantity,
            "sales": r.sales,
            "profit": r.profit,
        }
        for r in records
    ]


@router.get("/records/{row_id}", dependencies=[Depends(verify_token)])
def get_record_by_id(row_id: int, db: Session = Depends(get_db)):
    record = db.query(SalesRecord).filter(SalesRecord.row_id == row_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@router.put("/records/{row_id}", dependencies=[Depends(verify_token)])
def edit_record(row_id: int, updates: SalesRecordUpdate, db: Session = Depends(get_db)):
    record = db.query(SalesRecord).filter(SalesRecord.row_id == row_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    for key, value in updates.model_dump(exclude_unset=True).items():
        setattr(record, key, value)
    db.commit()
    return record

@router.delete("/records/{row_id}", dependencies=[Depends(verify_token)])
def delete_record(row_id: int, db: Session = Depends(get_db)):
    record = db.query(SalesRecord).filter(SalesRecord.row_id == row_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    db.delete(record)
    db.commit()
    return {"message": f"Deleted record with row_id {row_id}"}