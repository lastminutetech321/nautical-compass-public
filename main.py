from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
  return {"message": "Nautical Compass is live"}

@app.get("/intake")
def intake():
  return {"message": "Intake system active"}
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
  return FileResponse("favicon.png")
