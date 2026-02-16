from fastapi import FastAPI
from app.intake.router import router as intake_router

app = FastAPI(title="Nautical Compass")

app.include_router(intake_router)

@app.get("/")
def root():
    return {"status": "Nautical Compass is live"} 
