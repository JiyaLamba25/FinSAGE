from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.security import create_access_token, verify_login

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/auth/login")
def login(req: LoginRequest):
    if not verify_login(req.username, req.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token()
    return {"access_token": token, "token_type": "bearer"}