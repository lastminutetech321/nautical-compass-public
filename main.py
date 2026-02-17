from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
  return {"message": "Nautical Compass is live"}

@app.get("/intake")
def intake():
  return {"message": "Intake system active"}
