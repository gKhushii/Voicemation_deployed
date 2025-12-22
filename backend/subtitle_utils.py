import os
import tempfile
import uuid
import re
from typing import List, Dict, Any
from typing import List, Dict
from mutagen.mp3 import MP3
import subprocess

def generate_srt_file(explanation_text: str, audio_duration: float, index: int) -> str:
    """
    Creates a time-synced SubRip (.srt) file for a single narration segment.
    Simulates word timings by dividing the total duration based on the number of characters 
    in each sentence-like chunk.
    
    :param explanation_text: The narration text for the scene.
    :param audio_duration: The exact duration of the generated voiceover in seconds.
    :param index: The scene index (used for unique filename generation).
    :return: The absolute path to the generated .srt file.
    """
    
    # --- Step 1: Split text into sentence-like chunks ---
    # Using a simple split pattern to create natural subtitle breaks
    text_chunks = []
    current_chunk = ""
    # Use simple delimiters to break the text into manageable subtitle segments
    delimiters = re.compile(r'([.?!:;\n]| {2,})') 
    
    parts = delimiters.split(explanation_text)
    temp_chunk = ""
    
    for part in parts:
        if part and part.strip():
            temp_chunk += part
            if part.strip() in ['.', '?', '!', ':', ';'] or '\n' in part:
                text_chunks.append(temp_chunk.strip())
                temp_chunk = ""
                
    if temp_chunk.strip():
        text_chunks.append(temp_chunk.strip())

    if not text_chunks:
        # Fallback to single chunk if parsing fails
        text_chunks = [explanation_text.strip()]

    # --- Step 2: Allocate time based on character count ---
    total_chars = sum(len(chunk) for chunk in text_chunks)
    
    srt_content = []
    current_time = 0.0
    subtitle_index = 1

    for chunk in text_chunks:
        char_count = len(chunk)
        # Calculate duration proportional to character count
        duration = audio_duration * (char_count / total_chars)
        
        # Ensure the final chunk exactly hits the audio_duration
        if chunk == text_chunks[-1]:
            duration = audio_duration - current_time

        end_time = current_time + duration
        
        # Helper function to convert seconds to SRT time format (HH:MM:SS,MS)
        def seconds_to_srt_time(seconds):
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            sec = int(seconds % 60)
            ms = int((seconds - math.floor(seconds)) * 1000)
            return f"{hours:02}:{minutes:02}:{sec:02},{ms:03}"

        start_time_str = seconds_to_srt_time(current_time)
        end_time_str = seconds_to_srt_time(end_time)
        
        # Build SRT block
        srt_content.append(str(subtitle_index))
        srt_content.append(f"{start_time_str} --> {end_time_str}")
        srt_content.append(chunk)
        srt_content.append("") # Blank line separator
        
        current_time = end_time
        subtitle_index += 1
        
    # --- Step 3: Save to file ---
    temp_dir = tempfile.gettempdir()
    unique_filename = f"scene_{index}_subs_{uuid.uuid4().hex[:4]}.srt"
    srt_path = os.path.join(temp_dir, unique_filename)
    
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_content))
        
    print(f"📄 Generated SRT file: {srt_path}")
    return srt_path

# Note: The 'math' import is required for the time calculation.
import math
def parse_srt_to_json(srt_path):
    """
    Converts an SRT file into a list of dicts: {"start": float, "end": float, "text": str}
    Times are in seconds.
    """
    subtitles = []

    time_pattern = re.compile(r"(\d+):(\d+):(\d+),(\d+)")

    def srt_time_to_seconds(h, m, s, ms):
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms)/1000

    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = content.strip().split("\n\n")
    for block in blocks:
        lines = block.split("\n")
        if len(lines) >= 3:
            match = re.findall(r"\d+:\d+:\d+,\d+", lines[1])
            if len(match) == 2:
                h, m, s, ms = map(int, re.split(r"[:,]", match[0]))
                start = srt_time_to_seconds(h, m, s, ms)
                h, m, s, ms = map(int, re.split(r"[:,]", match[1]))
                end = srt_time_to_seconds(h, m, s, ms)
                text = " ".join(lines[2:])
                subtitles.append({"start": start, "end": end, "text": text})

    return subtitles

def get_video_duration(video_path: str) -> float:
    """Return duration in seconds using ffprobe (more reliable than reading filenames)."""
    if not video_path or not os.path.exists(video_path):
        return 0.0
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(res.stdout.strip())
    except Exception:
        return 0.0


def merge_and_offset_srt_files(srt_paths: List[str], rendered_videos: List[str]) -> List[Dict]:
    """
    Merge multiple per-scene SRT files into a single subtitle timeline in JSON.
    Offsets each scene's subtitles by the cumulative durations of prior scenes
    based on the durations of the *rendered* videos (rendered_videos list aligned with srt_paths).
    Returns: list of {"start": float, "end": float, "text": str}
    """
    merged = []
    if not srt_paths:
        return merged

    # cumulative offset (seconds)
    offset = 0.0

    # for safety: if rendered_videos provided, use their durations; else, fallback to last time in srt
    for idx, srt_path in enumerate(srt_paths):
        if not srt_path or not os.path.exists(srt_path):
            # still increment offset by rendered video length if available
            if idx < len(rendered_videos) and rendered_videos[idx]:
                offset += get_video_duration(rendered_videos[idx]) or 0.0
            continue

        subtitle_entries = parse_srt_to_json(srt_path)  # returns list of dicts with start/end in seconds
        for entry in subtitle_entries:
            merged.append({
                "start": round(entry["start"] + offset, 3),
                "end": round(entry["end"] + offset, 3),
                "text": entry["text"]
            })

        # increment offset by the rendered duration for this scene if available, else by last subtitle end
        if idx < len(rendered_videos) and rendered_videos[idx] and os.path.exists(rendered_videos[idx]):
            d = get_video_duration(rendered_videos[idx])
            offset += d or (subtitle_entries[-1]["end"] if subtitle_entries else 0.0)
        else:
            offset += subtitle_entries[-1]["end"] if subtitle_entries else 0.0

    # Optional: merge adjacent entries with same text or very close times (not strictly necessary)
    return merged