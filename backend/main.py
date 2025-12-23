# main.py — Render-safe FastAPI backend for Voicemation

from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

import os
import uuid
import tempfile
import subprocess
import traceback
import speech_recognition as sr

from voicemation import process_speech
from subtitle_utils import parse_srt_to_json

# -----------------------
# App setup
# -----------------------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # adjust later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg")

# In-memory job store (OK for demos)
jobs = {}

# -----------------------
# Helpers
# -----------------------

def ffprobe_duration(path: str) -> float:
    try:
        proc = subprocess.run(
            [FFMPEG_BIN.replace("ffmpeg", "ffprobe"),
             "-v", "error",
             "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1",
             path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        return float(proc.stdout.strip())
    except Exception:
        return 0.0


def scale_subtitles_to_video(subs, video_duration):
    if not subs:
        return subs

    last_end = subs[-1]["end"]
    if last_end <= 0:
        return subs

    scale = video_duration / last_end
    scaled = []

    for s in subs:
        start = round(s["start"] * scale, 3)
        end = round(s["end"] * scale, 3)
        if end <= start:
            end = start + 0.01
        scaled.append({
            "start": start,
            "end": end,
            "text": s["text"]
        })

    return scaled


# -----------------------
# Background job
# -----------------------

def run_generation_job(job_id: str, wav_path: str, manual_duration: int | None):
    try:
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            speech_text = recognizer.recognize_google(audio_data)

        video_path, srt_files = process_speech(
            speech_text,
            return_srt=True,
            manual_duration=manual_duration,
        )

        subtitles = []
        for srt in srt_files or []:
            if os.path.exists(srt):
                subtitles.extend(parse_srt_to_json(srt))

        duration = ffprobe_duration(video_path)
        if subtitles and duration > 0:
            subtitles = scale_subtitles_to_video(subtitles, duration)

        jobs[job_id] = {
            "status": "done",
            "video_path": video_path,
            "subtitles": subtitles,
            "duration": duration,
        }

    except Exception as e:
        jobs[job_id] = {
            "status": "error",
            "error": str(e),
            "trace": traceback.format_exc(),
        }
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)


# -----------------------
# Routes
# -----------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/generate_audio")
async def generate_audio(
    background_tasks: BackgroundTasks,
    audio: UploadFile = File(...),
    duration_limit: int = Form(0),
):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "processing"}

    manual_duration = duration_limit if duration_limit > 0 else None

    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
        tmp.write(await audio.read())
        webm_path = tmp.name

    wav_fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(wav_fd)

    try:
        subprocess.run(
            f'"{FFMPEG_BIN}" -y -i "{webm_path}" "{wav_path}"',
            shell=True,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ffmpeg failed: {e}")
    finally:
        if os.path.exists(webm_path):
            os.remove(webm_path)

    background_tasks.add_task(
        run_generation_job,
        job_id,
        wav_path,
        manual_duration,
    )

    return {
        "job_id": job_id,
        "status": "processing",
    }


@app.get("/status/{job_id}")
def get_status(job_id: str):
    return jobs.get(job_id, {"status": "unknown"})


@app.get("/download/{job_id}")
def download_video(job_id: str):
    job = jobs.get(job_id)
    if not job or job.get("status") != "done":
        raise HTTPException(status_code=404, detail="Video not ready")

    return FileResponse(job["video_path"], media_type="video/mp4")
