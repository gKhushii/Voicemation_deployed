import os 
import re 
import subprocess
import speech_recognition as sr
from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import SystemMessage, UserMessage
from azure.core.credentials import AzureKeyCredential
from voiceover_utils import generate_voiceover, add_voiceover_to_video
from subtitle_utils import generate_srt_file  # or wherever you saved it

from dotenv import load_dotenv

# extra imports for syncing / file discovery
from mutagen.mp3 import MP3
import uuid
import time

load_dotenv()

import re

# -------------------------
# Configuration
# -------------------------
FINAL_VIDEO_DIR = os.path.join(os.getcwd(), "output_videos")
os.makedirs(FINAL_VIDEO_DIR, exist_ok=True)

def sanitize_manim_code(manim_code: str) -> str:
    """
    Cleans up common GPT mistakes for Manim v0.18 compatibility.
    Fixes:
    - Unicode/punctuation issues
    - font_size/color/scale_tips/width-height-depth incompatibilities
    - move_to / next_to errors
    - arrange_in_grid alignment KeyErrors
    """
    code = manim_code.encode("utf-8", "ignore").decode("utf-8")

    # --- 1. Unicode / Punctuation Replacements ---
    replacements = {
        "×": "*", "÷": "/", "−": "-", "‒": "-", "–": "-", "—": "-",
        "“": '"', "”": '"', "‘": "'", "’": "'", "©": "(c)", "™": "(tm)",
        "°": "deg"
    }
    for bad, good in replacements.items():
        code = code.replace(bad, good)

    # --- 2. Manim API Compatibility Fixes ---
    code = re.sub(r'get_text\(([^)]*?),\s*font_size\s*=\s*\d+\)', r'get_text(\1).scale(0.7)', code)
    code = re.sub(r'get_text\("([^"]+)"\s*,\s*color\s*=\s*([A-Z_]+)\)', r'get_text("\1").set_color(\2)', code)
    code = re.sub(r',?\s*scale_tips\s*=\s*(?:True|False|t|f)', r'', code)
    code = re.sub(r',\s*(width|height|depth)\s*=\s*[\d\.]+', r'', code)
    code = re.sub(r'\b(width|height|depth)\s*=\s*[\d\.]+,?\s*', r'', code)

    # --- 3. move_to / next_to fixes ---
    code = re.sub(r'(\.move_to)(?!\s*\()', r'.move_to(ORIGIN)', code)
    code = re.sub(r'next_to\(\s*\[.*?\]\s*,', r'next_to(ORIGIN,', code)
    code = re.sub(r'next_to\(\s*ORIGIN\s*,\s*([A-Z_]+)', r'next_to(ORIGIN, \1, buff=0.3)', code)
    code = re.sub(r'\.to_edge\s*\(\s*CENTER\s*(,\s*buff\s*=\s*\d+)?\s*\)', '.move_to(ORIGIN)', code)
    code = code.replace("BROWN", "MAROON")
    code = code.replace("brown", "MAROON")
    code = re.sub( 
    r'SVGMobject\(".*?"[^\)]*\)',
    'Circle(radius=0.5, color=GRAY, fill_opacity=0.7)',
    code
)

    # --- 4. arrange_in_grid alignment fixes ---
    def fix_alignments(match):
        original = match.group(0)

        # Fix col_alignments
        col_align_match = re.search(r'col_alignments\s*=\s*([^\s,)]+)', original)
        if col_align_match:
            col_align = col_align_match.group(1).strip(' "\'')
            col_align = ''.join([c for c in col_align if c in "lcr"]) or "c"
            original = re.sub(r'col_alignments\s*=\s*[^\s,)]+', f'col_alignments="{col_align}"', original)

        # Fix row_alignments
        row_align_match = re.search(r'row_alignments\s*=\s*([^\s,)]+)', original)
        if row_align_match:
            row_align = row_align_match.group(1).strip(' "\'')
            row_align = ''.join([c for c in row_align if c in "lcr"]) or "c"
            original = re.sub(r'row_alignments\s*=\s*[^\s,)]+', f'row_alignments="{row_align}"', original)

        return original

    code = re.sub(r'\.arrange_in_grid\([^\)]*\)', fix_alignments, code)

    # --- 5. Clean trailing spaces ---
    code = re.sub(r'\s+$', '', code, flags=re.MULTILINE)

    return code



# -------------------------
# NEW: Duration selection (B1) + auto-estimation (C)
# -------------------------
# def get_desired_duration(user_topic: str) -> int:
#     """
#     Terminal menu for user to pick a duration.
#     If user presses Enter (no input), AI auto-estimates based on topic.
#     Returns duration in seconds.
#     Allowed choices: 30, 60, 120, 180, 300
#     """
#     print("\n📌 Choose desired animation duration:")
#     print("1. 30 seconds")
#     print("2. 1 minute")
#     print("3. 2 minutes")
#     print("4. 3 minutes")
#     print("5. 5 minutes")
#     print("Press ENTER to let AI decide automatically.\n")

#     try:
#         choice = input("Enter choice (1–5 or press Enter): ").strip()
#     except (EOFError, KeyboardInterrupt):
#         # If input not possible (non-interactive), fall back to auto estimate
#         choice = ""

#     duration_map = {
#         "1": 30,
#         "2": 60,
#         "3": 120,
#         "4": 180,
#         "5": 300
#     }

#     if choice in duration_map:
#         selected = duration_map[choice]
#         print(f"🕒 User selected duration: {selected} seconds\n")
#         return selected

#     # Auto mode (C)
#     print("🤖 No duration chosen — AI will estimate based on topic.\n")
#     # Basic heuristic: word count + presence of complexity keywords
#     words = user_topic.split()
#     length = len(words)

#     # complexity keywords (small heuristic; GPT will refine further)
#     complex_keywords = [
#         "cocomo", "compiler", "operating system", "neural", "transform", "fourier",
#         "concurrency", "blockchain", "distributed", "encryption", "bayesian"
#     ]
#     medium_keywords = [
#         "quicksort", "dynamic programming", "recursion", "graphs", "topology",
#         "big o", "sorting", "search", "hash", "binary tree"
#     ]

#     topic_lower = user_topic.lower()
#     if any(k in topic_lower for k in complex_keywords):
#         return 180  # 3 min for complex subjects
#     if any(k in topic_lower for k in medium_keywords):
#         return 120  # 2 min for medium subjects

#     # fallback based on length
#     if length < 6:
#         return 30
#     elif length < 15:
#         return 60
#     elif length < 30:
#         return 120
#     else:
#         return 180



def estimate_duration_auto(user_topic: str) -> int:
    """
    Fully automatic duration estimation.
    No user input, safe for backend & deployment.
    """
    words = user_topic.split()
    length = len(words)

    complex_keywords = [
        "compiler", "operating system", "neural", "transformer",
        "fourier", "blockchain", "distributed", "encryption"
    ]
    medium_keywords = [
        "recursion", "dynamic programming", "graphs",
        "sorting", "binary tree", "hashing"
    ]

    topic_lower = user_topic.lower()

    if any(k in topic_lower for k in complex_keywords):
        return 180   # 3 min
    if any(k in topic_lower for k in medium_keywords):
        return 120   # 2 min

    if length < 6:
        return 30
    elif length < 15:
        return 60
    elif length < 30:
        return 120
    else:
        return 180

# -------------------------
# NEW: extract all sections (explanation + code blocks)
# -------------------------
def extract_all_sections(gpt_response):
    """
    Parse the GPT response and return a list of sections:
    [ {'explanation': <text before code block>, 'code': <code>}, ... ]

    This handles multiple ```python ... ``` blocks in a single response.
    If the response contains text before the first block, it's treated as
    the introduction explanation for section 0 (if no code), or paired to first code block.
    """
    code_block_pattern = re.compile(r"```(?:python)?\n([\s\S]*?)```", re.MULTILINE)
    matches = list(code_block_pattern.finditer(gpt_response))

    sections = []
    if not matches:
        # no code blocks — return the whole response as explanation with no code
        return [{'explanation': gpt_response.strip(), 'code': None}]

    # text before the first code block
    prev_end = 0
    for m in matches:
        start = m.start()
        code = m.group(1).strip()
        explanation = gpt_response[prev_end:start].strip()
        # If explanation is empty (common), try to extract a small heading above the block
        sections.append({'explanation': explanation, 'code': code})
        prev_end = m.end()

    # any trailing text after the last code block — append to last explanation
    trailing = gpt_response[prev_end:].strip()
    if trailing:
        # append trailing to the last section's explanation
        if sections:
            if sections[-1]['explanation']:
                sections[-1]['explanation'] += "\n\n" + trailing
            else:
                sections[-1]['explanation'] = trailing
        else:
            sections.append({'explanation': trailing, 'code': None})

    # Normalize: if first section's explanation is empty, leave as empty string
    for s in sections:
        if s['explanation'] is None:
            s['explanation'] = ""

    return sections


# -------------------------
# keep existing extract_explanation_and_code for backward compatibility
# -------------------------
def extract_explanation_and_code(gpt_response):
    """
    Legacy single-block extractor (kept for compatibility).
    """
    match = re.search(r"```(?:python)?\n([\s\S]*?)```", gpt_response)
    if match:
        code = match.group(1).strip()
        explanation = gpt_response[:match.start()].strip()
        return explanation, code
    return gpt_response, None


# -------------------------
# GPT request (modified to accept desired_duration, but otherwise same)
# -------------------------
# ... (rest of the script remains the same)

def get_gpt_response(speech_text, desired_duration):
    endpoint = "https://models.github.ai/inference"
    model = "gpt-4.1"
    token = os.environ.get("GITHUB_TOKEN", "")

    client = ChatCompletionsClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(token),
    )

    # --- DYNAMIC INSTRUCTION GENERATION BASED ON DURATION ---
    duration_minutes = desired_duration / 60
    
    # Determine Animation Detail and Scene Count Range (Flexible)
    if duration_minutes <= 0.5:  # 30 seconds
        detail = "VERY short and simple"
        scene_range = "1-2 SCENES"
        num_scenes_instruction = "aim for 1 to 2 SCENES"
    elif duration_minutes <= 1.0:  # 1 minute
        detail = "short and simple"
        scene_range = "3-5 SCENES" # Adjusted from 3-6
        num_scenes_instruction = "aim for 3 to 5 SCENES" # Adjusted from 3 to 6
    elif duration_minutes <= 2.0:  # 2 minutes
        detail = "NORMAL detail"
        scene_range = "5-8 SCENES" # Adjusted from 6-9
        num_scenes_instruction = "aim for 5 to 8 SCENES" # Adjusted from 6 to 9
    elif duration_minutes <= 3.0:  # 3 minutes
        detail = "DETAIL and thorough"
        scene_range = "8-12 SCENES" 
        num_scenes_instruction = "aim for 8 to 12 SCENES"
    else:  # 5 minutes (or more)
        detail = "VERY DETAIL and extensive"
        scene_range = "12-16 SCENES"
        num_scenes_instruction = "aim for 12 to 16 SCENES"

    # --- START MODIFIED SYSTEM PROMPT ---
    system_prompt = (
        " You are an assistant that converts user speech into Manim animations. "
        "Always respond ONLY with valid Python Manim code wrapped in triple backticks. "
        "Do not include explanations, markdown, or text outside the code block."
        "Important: In Manim Community v0.18, `Brace.get_text()` does not take `font_size`. "
        "If you need to resize text, use `.scale()` after creating the text."
        "You are an assistant that generates BOTH:\n"
        "1. A short natural language explanation of the concept (for voiceover).\n"
        "2. Valid Manim Community v0.18 Python code (inside triple backticks).\n\n"
        "⚠️ Important rules:\n"
        "- Wrap ONLY the code in triple backticks.\n"
        "- Do NOT wrap the explanation in code blocks.\n"
        "- Do NOT include markdown or text outside explanation + code.\n\n"
        
        # <<< DYNAMIC SCENE GENERATION CONSTRAINT (FINAL FLEXIBLE VERSION) >>>
        f"### DYNAMIC ANIMATION CONSTRAINT (MANDATORY) ###\n"
        f"Current Duration: {desired_duration} seconds ({duration_minutes:.1f} minutes).\n"
        f"Animation Detail Level MUST be: **{detail.upper()}**.\n"
        f"**FLEXIBLE SCENE COUNT:** Split the content into multiple short, sequential Manim SCENES (Scene subclasses), and **{num_scenes_instruction}**.\n"
        f"The scene count is a flexible guideline. Prioritize natural flow and pacing that meets the total duration, even if it slightly deviates from the number of scenes suggested.\n"
        f"####################################################\n"
        # <<< END DYNAMIC SCENE CONSTRAINT >>>

        "### VISUAL LAYOUT & OVERLAP CONSTRAINT (MANDATORY) ###\n"
        "You MUST ensure all Mobjects are clearly separated and DO NOT overlap. Use Manim's layout tools extensively:\n"
        "1. **Positioning:** Use `Mobject.next_to()`, `Mobject.to_edge()`, or `Mobject.move_to()` to prevent crowding.\n"
        "2. **Grouping & Spacing:** Use `VGroup` (vertical) and `HGroup` (horizontal) and ALWAYS include a `buff` parameter (e.g., `buff=0.7`) in `.arrange()` to add clear space between elements.\n"
        "3. **Clear Regions:** Design the scene by allocating specific, non-overlapping regions for different visual concepts (Input, Process, Output).\n"
        "##########################################################\n"

        "STRICT CONSTRAINT: DO NOT use external files. Only use built-in Manim Mobjects (Circle, Square, Text, MathTex, Line, Arrow, VGroup, etc.) and primitives. Do NOT use SVGMobject or ImageMobject with filenames."
        
        f"TOTAL_TARGET_SECONDS: {desired_duration}\n"
        "Based on the target duration, split the explanation into multiple short, sequential Manim SCENES (Scene subclasses), and **{num_scenes_instruction}** to approximate the requested total duration.\n"
        "For each scene, include only valid Manim code wrapped in triple backticks.\n"
        "Also include short plain-text explanation paragraphs before each code block for narration (do not place those explanations inside code blocks)."
    )
    # --- END MODIFIED SYSTEM PROMPT ---
    
    response_object = client.complete(
        messages=[
            SystemMessage(system_prompt),
            UserMessage(speech_text),
        ],
        temperature=0.7,
        top_p=1.0,
        model=model
    )
    
    # CRITICAL FIX: Extract the text content from the response object
    if response_object.choices and response_object.choices[0].message:
        return response_object.choices[0].message.content
    
    return ""
# ... (rest of the script remains the same)


# Keep old single-block extractor (still used in some places)
def extract_manim_code(gpt_response):
    match = re.search(r"```(?:python)?\n([\s\S]*?)```", gpt_response)
    if match:
        code = match.group(1).strip()
        print("✅ Extracted Python code successfully.")
        return code
    else:
        print("❌ No valid Python code block found in GPT response.")
        return None


# Extract Scene class name dynamically (kept)
def extract_class_name(manim_code):
    match = re.search(r"class\s+(\w+)\s*\(Scene\):", manim_code)
    if match:
        return match.group(1)
    return "Scene"


# Save code to a temp .py file (modified to accept index & unique filename)
def save_manim_code_to_temp_file(manim_code, index=0):
    unique_suffix = uuid.uuid4().hex[:8]
    filename = f"generated_manim_code_part_{index}_{unique_suffix}.py"
    temp_file_path = os.path.join(os.getenv("TEMP", "/tmp"), filename)

    with open(temp_file_path, "w", encoding="utf-8") as file:
        # 🔥 Automatically add required imports for Manim
        file.write("from manim import *\n\n")
        file.write(manim_code)

    print(f"📁 Saved Manim code to: {temp_file_path}")
    return temp_file_path



# helper: get audio duration (kept)
def get_audio_duration(audio_path):
    # This uses mutagen.mp3.MP3, which is suitable for MP3 files
    # If generate_voiceover produces other formats (e.g., wav), this may need adjustment.
    audio = MP3(audio_path)
    return audio.info.length  # seconds


# -------------------------
# NEW: find manim output for a given class name after rendering
# -------------------------
def find_manim_output_file(class_name, timeout=10):
    """
    Searches the 'media' directory for a mp4 named <class_name>.mp4.
    Waits up to `timeout` seconds for the file to appear (useful after subprocess).
    Returns the first matching path or None.
    """
    media_root = "media"
    deadline = time.time() + timeout
    found = None
    while time.time() < deadline:
        for root, dirs, files in os.walk(media_root):
            for f in files:
                if f == f"{class_name}.mp4":
                    found = os.path.join(root, f)
                    return found
        time.sleep(0.5)
    return None


# -------------------------
# Render a single Manim file and return the produced mp4 path
# -------------------------
def render_manim_file(temp_file_path, class_name, timeout_per_scene=180):
    """
    Runs manim for the given file and returns the output video path (or None).
    """
    command = ["manim", "-pql", temp_file_path, class_name]
    try:
        print("🎬 Running Manim command:", " ".join(command))
        subprocess.run(command, capture_output=True, text=True, check=True, timeout=timeout_per_scene)
        print("✅ Manim animation complete for", class_name)
        # attempt to find the output file
        video_path = find_manim_output_file(class_name, timeout=10)
        if video_path:
            print("📁 Found Manim output:", video_path)
            return video_path
        else:
            print("⚠️ Could not locate Manim output for class", class_name)
            return None
    except subprocess.CalledProcessError as e:
        print("❌ Manim execution error:")
        print("Output:", e.stdout)
        print("Errors:", e.stderr)
        return None
    except subprocess.TimeoutExpired:
        print("⏱ Manim command timed out.")
        return None


# -------------------------
# NEW: concatenate multiple videos into one final file (fast concat)
# -------------------------
def concatenate_videos(video_paths, output_path):
    """
    Concatenate videos using ffmpeg concat demuxer. If concat fails, falls back to re-encoding.
    """
    if not video_paths:
        return None
    if len(video_paths) == 1:
        # nothing to concatenate
        return video_paths[0]

    list_file = os.path.join(os.getenv("TEMP", "/tmp"), f"video_list_{uuid.uuid4().hex[:8]}.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        for vp in video_paths:
            f.write(f"file '{os.path.abspath(vp)}'\n")

    # Try fast concat
    cmd_concat = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file, "-c", "copy", output_path
    ]
    try:
        print("🔗 Concatenating videos (fast copy) ->", output_path)
        subprocess.run(cmd_concat, check=True, capture_output=True, text=True)
        print("✅ Concatenation successful (copy).")
        return output_path
    except subprocess.CalledProcessError as e:
        print("⚠️ Fast concat failed, trying re-encode concat. Error:", e)
        # Fallback: re-encode (slower but more compatible)
        cmd_reencode = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", list_file, "-c:v", "libx264", "-tune", "animation", "-c:a", "aac", output_path
        ]
        try:
            subprocess.run(cmd_reencode, check=True, capture_output=True, text=True)
            print("✅ Concatenation successful (re-encoded).")
            return output_path
        except subprocess.CalledProcessError as e2:
            print("❌ Concatenation failed:", e2)
            return None


# -------------------------
# Updated run_manim orchestration for multiple sections
# -------------------------
# --- ORIGINAL FUNCTIONALITY TO BE REPLACED ---
# def run_manim_for_sections(section_files_and_classes, all_explanations):
#    ... (renders all, THEN generates one combined voiceover, THEN merges)

# --- PROPOSED NEW STRUCTURE ---
def run_manim_for_sections(sections_to_process: list):
    synchronized_videos = []

    for idx, sec in enumerate(sections_to_process):
        temp_path = sec['temp_path']
        class_name = sec['class_name']
        explanation = sec['explanation']

        print(f"\n--- 🎬 Processing Scene {idx + 1} ({class_name}) ---")

        narration_path = generate_voiceover(explanation)
        if not os.path.exists(narration_path):
            print("❌ Voiceover generation failed.")
            continue

        narration_duration = get_audio_duration(narration_path)
        print(f"🔊 Narration duration: {narration_duration:.2f}s")

        try:
            srt_path = generate_srt_file(explanation, narration_duration, idx)
        except Exception as e:
            print("⚠️ Subtitle generation failed:", e)
            srt_path = None

        video_path_raw = render_manim_file(temp_path, class_name)
        if not video_path_raw:
            print("⚠️ Render failed.")
            continue

        video_with_vo = add_voiceover_to_video(
            video_path_raw,
            narration_path,
            narration_duration,
            subtitle_path=srt_path
        )

        if video_with_vo:
            synchronized_videos.append(video_with_vo)
            print(f"✅ Scene {idx + 1} synchronized.")
        else:
            print("⚠️ Merge failed.")

    if not synchronized_videos:
        print("❌ No scenes synchronized.")
        return None

    final_output = os.path.join(
        FINAL_VIDEO_DIR,
        f"final_synced_{uuid.uuid4().hex[:8]}.mp4"
    )

    final_merged = concatenate_videos(synchronized_videos, final_output)

    if final_merged:
        final_merged = os.path.abspath(final_merged)
        print("🎉 Final video ready at:", final_merged)
        print("📁 Exists:", os.path.exists(final_merged))
        return final_merged

    print("❌ Final merge failed.")
    return None

# -------------------------
# Process speech (modified to produce multiple segments)
# -------------------------
# --- MODIFIED process_speech FUNCTION ---
# voicemation.py
from mutagen.mp3 import MP3

def process_speech(speech_text, return_srt=False, manual_duration=None):
    """
    Process speech to generate animation.

    :param speech_text: Text to generate animation for
    :param return_srt: Boolean to also return SRT files
    :param manual_duration: Optional duration in seconds, overrides AI
    """
    if "exit" in speech_text.lower():
        print("Exiting program...")
        return (None, None) if return_srt else None

    # Use manual duration if provided, else let AI decide automatically
    if manual_duration is not None:
        desired_duration = manual_duration
        print(f"⏱ Using manual duration: {desired_duration}s")
    else:
        desired_duration = estimate_duration_auto(speech_text)
        print(f"🧠 AI auto-estimated duration: ~{desired_duration}s")

    gpt_response = get_gpt_response(speech_text, desired_duration)
    sections = extract_all_sections(gpt_response)

    sections_to_process = []
    srt_files = []

    for idx, sec in enumerate(sections, start=1):
        explanation = sec.get('explanation', '') or ''
        code = sec.get('code')

        if code:
            code_clean = sanitize_manim_code(code)
            temp_path = save_manim_code_to_temp_file(code_clean, index=idx)
            class_name = extract_class_name(code_clean)

            sections_to_process.append({
                'temp_path': temp_path,
                'class_name': class_name,
                'explanation': explanation
            })

            if return_srt:
                voiceover_path = generate_voiceover(explanation)
                audio = MP3(voiceover_path)
                audio_duration = audio.info.length
                srt_path = generate_srt_file(explanation, audio_duration, idx)
                srt_files.append(srt_path)

        elif explanation.strip():
            print(f"⚠️ Skipping pure explanation block (Section {idx}) as it contains no Manim code.")
            if return_srt:
                voiceover_path = generate_voiceover(explanation)
                audio = MP3(voiceover_path)
                audio_duration = audio.info.length
                srt_path = generate_srt_file(explanation, audio_duration, idx)
                srt_files.append(srt_path)

    if not sections_to_process:
        print("❌ No valid Manim code generated in any section.")
        return (None, None) if return_srt else None

    final_video = run_manim_for_sections(sections_to_process)

    if return_srt:
        return final_video, srt_files
    return final_video


# -------------------------
# Main speech recognition loop (kept with small improvement to use listen)
# -------------------------
if __name__ == "__main__":
    recognizer = sr.Recognizer()

    while True:
        with sr.Microphone() as source:
            print("\n🎤 Listening for animation commands (say 'exit' to quit)...")

            # Adjust to ambient noise before listening
            recognizer.adjust_for_ambient_noise(source, duration=1)
            print("🕒 You can start speaking now...")

            try:
                print("speak...")
                # use listen with phrase_time_limit for better UX
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=12)

                speech_text = recognizer.recognize_google(audio)
                print(f"🗣 Recognized: {speech_text}")
                if not process_speech(speech_text):
                    break
            except sr.WaitTimeoutError:
                print("⏳ No speech detected, try again.")
            except sr.UnknownValueError:
                print("🤷 Could not understand the audio.")
            except sr.RequestError:
                print("🚫 Speech recognition service is unavailable.")
            except KeyboardInterrupt:
                print("\n🛑 Program terminated.")
                break