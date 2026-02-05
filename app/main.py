from fastapi import FastAPI
from app.intake import router

app = FastAPI(title="Nautical Compass Intake")
app.include_router(router)
