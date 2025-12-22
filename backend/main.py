from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from voicemation import process_speech

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # later restrict to Vercel domain
    allow_methods=["*"],
    allow_headers=["*"],
)

class GenerateRequest(BaseModel):
    text: str

@app.post("/generate")
def generate(req: GenerateRequest):
    video_path = process_speech(req.text)
    return {
        "status": "success",
        "video_path": video_path
    }
