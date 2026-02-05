from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

class Intake(BaseModel):
    role: str
    context: str
    narrative: str

@router.post("/intake")
def submit_intake(data: Intake):
    return {
        "status": "received",
        "timestamp": datetime.utcnow().isoformat()
    }
