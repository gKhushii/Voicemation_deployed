#voiceover.utils.py
import os
import subprocess
import tempfile
from gtts import gTTS
import uuid

# --- Synchronization Utility: Audio Duration ---

def get_audio_duration(audio_path):
    """
    CRITICAL STEP for sync: Uses FFprobe to get the exact duration of the audio file.
    Requires 'ffprobe' to be installed and accessible in the system PATH.
    """
    if not os.path.exists(audio_path):
        print(f"❌ Audio file not found for duration check: {audio_path}")
        return 0.0

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]

    try:
        # Run ffprobe and capture the output (the duration string)
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        duration_seconds = float(result.stdout.strip())
        return duration_seconds
    except Exception as e:
        print(
            f"❌ FFprobe failed to get audio duration. Ensure FFprobe is installed and in PATH. Error: {e}"
        )
        return 0.0


# --- Voiceover Generation ---

def generate_voiceover(text):
    """
    Convert input text to speech using gTTS and save as MP3.
    Uses a unique temporary filename.
    """
    # Use a secure temp path
    temp_dir = tempfile.gettempdir()
    # Use a unique filename is essential for concurrent processing
    temp_audio_path = os.path.join(temp_dir, f"voiceover_{uuid.uuid4().hex[:8]}.mp3")

    try:
        tts = gTTS(text)
        tts.save(temp_audio_path)
        print(f"🔊 Voiceover saved to: {temp_audio_path}")
        return temp_audio_path
    except Exception as e:
        print(f"❌ gTTS failed to generate voiceover: {e}")
        return None


# --- Video/Audio Merging (SUBTITLE LOGIC REMOVED) ---

def add_voiceover_to_video(video_path, audio_path, audio_duration_seconds, subtitle_path=None):
    """
    Merges video and audio using ffmpeg.
    The subtitle_path parameter is now ignored, as subtitles are handled by the frontend.
    """
    if not os.path.exists(video_path):
        print(f"❌ Video not found at: {video_path}")
        return None

    # Generate a unique path for the synchronized output
    temp_dir = tempfile.gettempdir()
    unique_filename = f"synced_video_{uuid.uuid4().hex[:8]}.mp4"
    output_path = os.path.join(temp_dir, unique_filename)

    # 🟢 Base FFmpeg Command (Synchronization) 🟢
    command = [
        "ffmpeg",
        "-y",
        "-stream_loop",
        "-1",
        # Input 0: Video (looped)
        "-i",
        video_path,
        # Input 1: Audio 
        "-i",
        audio_path,
        # Output duration matches audio length
        "-t",
        str(audio_duration_seconds),
        # Use video stream from first input (0)
        "-map",
        "0:v:0",
        # Use audio stream from second input (1)
        "-map",
        "1:a:0",
        "-c:v",
        "libx264",
        "-tune",
        "animation",
        "-c:a",
        "aac",
    ]
    
    # 🚫 Note: The FFmpeg command now contains NO subtitle filter.

    # Append the final output path
    command.append(output_path)

    # --- EXECUTION ---
    try:
        print("🎞️ Merging video and voiceover using ffmpeg...")
        subprocess.run(command, check=True, capture_output=True, text=True)
        print(f"✅ Final synchronized video saved at: {output_path}")
        return output_path

    except subprocess.CalledProcessError as e:
        print(f"❌ ffmpeg failed during merging.")
        print("--- ffmpeg ERROR DETAILS (last 5 lines) ---")
        print("\n".join(e.stderr.splitlines()[-5:]))
        print("----------------------------")
        return None