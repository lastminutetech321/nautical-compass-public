from fastapi import APIRouter

router = APIRouter()

@router.get("/intake")
def intake_home():
    return {"message": "Intake system active"}
