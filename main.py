from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI()

class IntakeForm(BaseModel):
  name:str
  email:str
  service_requested: str
  note:str | None = None

@app.get("/") 
def root():
    return {"message": "Nautical Compass is live"}

@app.get("/intake")
def intake_info():
    return {"message": "Submit intake via Post request to /intake"}

  @app.post("/intake")
  def submit_intake(form: IntakeForm):
      return {
          "status": "Intake received",
          "data": form
    }

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse("favicon.png")
