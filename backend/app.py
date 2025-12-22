# app.py  — clean backend for Voicemation

from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import os
import tempfile
import subprocess
import traceback
 
import speech_recognition as sr

from voicemation import process_speech   # your pipeline
from subtitle_utils import parse_srt_to_json

app = Flask(__name__)
CORS(app)

# do NOT use debug=True in production-style runs
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

OUTPUT_VIDEO = None  # store the latest video path
FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg")


# -----------------------
# Helpers
# -----------------------
def ffprobe_duration(path: str) -> float:
    """Return duration in seconds (float) or 0 on failure."""
    try:
        proc = subprocess.run(
            [FFMPEG_BIN.replace("ffmpeg", "ffprobe"), "-v", "error",
             "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        return float(proc.stdout.strip())
    except Exception as e:
        print("ffprobe failed:", e)
        return 0.0


def scale_subtitles_to_video(subs, video_duration):
    """
    Linearly scale subtitles timestamps so the full subtitle
    timeline fits the final video duration.
    subs: list of {"start": float, "end": float, "text": str}
    """
    if not subs:
        return subs

    last_sub_end = subs[-1]["end"]
    if last_sub_end <= 0:
        return subs

    if abs(video_duration - last_sub_end) < 1.0:
        # close enough; don’t bother scaling
        return subs

    scale = video_duration / last_sub_end
    print(f"Scaling subtitles by factor {scale:.3f} ({last_sub_end:.2f}s -> {video_duration:.2f}s)")

    scaled = []
    for e in subs:
        s = round(e["start"] * scale, 3)
        ed = round(e["end"] * scale, 3)
        if ed <= s:
            ed = s + 0.01
        scaled.append({"start": s, "end": ed, "text": e["text"]})
    return scaled


# -----------------------
# Routes
# -----------------------

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/download")
def download():
    global OUTPUT_VIDEO
    if OUTPUT_VIDEO and os.path.exists(OUTPUT_VIDEO):
        return send_file(OUTPUT_VIDEO, as_attachment=False)
    return jsonify({"error": "No video generated yet."}), 404


@app.route("/generate_audio", methods=["POST"])
def generate_audio():
    """
    Accepts 'audio' (webm) and optional form field 'duration_limit'
    duration_limit = '0' -> AI decides
    otherwise an integer -> seconds to force
    Returns: JSON { video_url: "/download", subtitles_json: [...] }
    """
    global OUTPUT_VIDEO

    if "audio" not in request.files:
        return jsonify({"error": "No audio uploaded"}), 400

    audio_file = request.files["audio"]
    duration_limit = request.form.get("duration_limit", "0")
    manual_duration = int(duration_limit) if duration_limit != "0" else None

    # save incoming webm -> temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp_webm:
        audio_file.save(tmp_webm.name)
        webm_path = os.path.abspath(tmp_webm.name)

    wav_fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(wav_fd)
    wav_path = os.path.abspath(wav_path)

    try:
        # ----------------------
        # ffmpeg: webm -> wav
        # ----------------------
        print("🔧 webm_path:", repr(webm_path))
        print("🔧 wav_path :", repr(wav_path))

        ffmpeg_cmd = f'"{FFMPEG_BIN}" -y -i "{webm_path}" "{wav_path}"'
        print("🔧 Running ffmpeg command:", ffmpeg_cmd)

        # Use shell=True on Windows to avoid Errno 22 argument issues
        subprocess.run(
            ffmpeg_cmd,
            shell=True,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # ----------------------
        # Speech recognition
        # ----------------------
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            speech_text = recognizer.recognize_google(audio_data)

        print("Recognized speech_text:", speech_text[:80])

    except sr.UnknownValueError:
        return jsonify({"error": "Could not understand audio"}), 400
    except sr.RequestError as e:
        print("Speech recognition request error:", e)
        return jsonify({"error": "Speech recognition service unavailable", "detail": str(e)}), 503
    except subprocess.CalledProcessError as e:
        # ffmpeg ran but failed (bad input, etc.)
        print("ffmpeg conversion failed (process error):", e)
        return jsonify({"error": "Failed to convert audio", "detail": str(e)}), 500
    except (FileNotFoundError, OSError) as e:
        # This is the Errno 22 case you keep seeing
        print("ffmpeg executable / argument error:", repr(e))
        return jsonify({
            "error": "ffmpeg executable or arguments invalid",
            "detail": str(e),
            "webm_path": webm_path,
            "wav_path": wav_path,
        }), 500
    except Exception as e:
        print("Unexpected error in audio handling:", e)
        traceback.print_exc()
        return jsonify({"error": "Audio handling error", "detail": str(e)}), 500
    finally:
        # DO NOT delete wav here if we still need it for recognition failure handling
        if os.path.exists(webm_path):
            os.remove(webm_path)
        if os.path.exists(wav_path):
            os.remove(wav_path)

    # ----------------------
    # Your Voicemation pipeline
    # ----------------------
    try:
        OUTPUT_VIDEO, srt_files = process_speech(
            speech_text,
            return_srt=True,
            manual_duration=manual_duration,
        )
    except TypeError:
        # legacy signature returning only video
        print("process_speech TypeError: assuming legacy signature")
        traceback.print_exc()
        OUTPUT_VIDEO = process_speech(speech_text)
        srt_files = []
    except Exception as e:
        print("Error in process_speech:", e)
        traceback.print_exc()
        return jsonify({
            "error": "Video generation failed",
            "detail": str(e),
        }), 500

    # ----------------------
    # Parse subtitles (if any)
    # ----------------------
    subtitles_json = []
    for srt_path in srt_files or []:
        try:
            if srt_path and os.path.exists(srt_path):
                subtitles_json.extend(parse_srt_to_json(srt_path))
        except Exception as e:
            print("Failed to parse srt:", srt_path, e)

    # ----------------------
    # Final video & duration
    # ----------------------
    if OUTPUT_VIDEO and os.path.exists(OUTPUT_VIDEO):
        video_duration = ffprobe_duration(OUTPUT_VIDEO)
        if video_duration > 0 and subtitles_json:
            subtitles_json = scale_subtitles_to_video(subtitles_json, video_duration)

        return jsonify({
            "video_url": "/download",
            "subtitles_json": subtitles_json,
            "final_duration": video_duration,
        }), 200
    else:
        return jsonify({"error": "Failed to generate video"}), 500


# -----------------------
# Global error handler (no more HTML debugger)
# -----------------------
from werkzeug.exceptions import HTTPException

@app.errorhandler(Exception)
def handle_exception(e):
    # If it's an HTTPException (404, 405, etc.), keep its status code
    if isinstance(e, HTTPException):
        print("HTTP error:", e)
        return jsonify({
            "error": e.name,
            "detail": e.description,
        }), e.code

    # Otherwise it's a real internal error
    tb = traceback.format_exc()
    print("Global error:", e)
    print(tb)

    return jsonify({
        "error": "Internal server error",
        "detail": str(e),
    }), 500




if __name__ == "__main__":
    print("🚀 STARTING ROOT APP.PY (PORT 5001)")
    app.run(debug=False, use_reloader=False, port=5001)
