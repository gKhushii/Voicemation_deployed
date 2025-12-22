import os
import subprocess
import speech_recognition as sr
from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import SystemMessage, UserMessage
from azure.core.credentials import AzureKeyCredential
import tempfile
import re

def process_speech(speech_text):
    # Exit condition
    if "exit" in speech_text.lower():
        print("Exiting program...")
        return False

    if "ohm" in speech_text.lower():
        print("Explaining Ohms Law with a Manim animation...")
        gpt_prompt = "Explain Ohms Law using a Manim animation OhmsLawScenes in Python."
        gpt_response = get_gpt_response(gpt_prompt)
        manim_code, scene_class = extract_manim_code_and_scene(gpt_response)

        if manim_code and scene_class:
            temp_file_path = save_manim_code_to_temp_file(manim_code)
            run_manim(temp_file_path, scene_class)
        else:
            print("Could not extract valid Manim code from GPT.")
    else:
        print("Command not recognized.")
    return True

def get_gpt_response(prompt):
    endpoint = "https://models.github.ai/inference"
    model = "openai/gpt-4.1"
    token = os.environ["GITHUB_TOKEN"]

    client = ChatCompletionsClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(token),
    )

    response = client.complete(
        messages=[
            SystemMessage("You are a helpful assistant."),
            UserMessage(prompt),
        ],
        temperature=1.0,
        top_p=1.0,
        model=model
    )

    gpt_response = response.choices[0].message.content
    print(f"GPT Response:\n{gpt_response}")
    return gpt_response

def extract_manim_code_and_scene(gpt_response):
    code_match = re.search(r"```python(.*?)```", gpt_response, re.DOTALL)
    if not code_match:
        print("⚠️ Could not find valid Python code block.")
        return None, None

    manim_code = code_match.group(1).strip()

    scene_match = re.search(r"class\s+(\w+)\(Scene\):", manim_code)
    if not scene_match:
        print("⚠️ Could not determine Scene class name.")
        return manim_code, "Scene"  # Fallback

    scene_class = scene_match.group(1)
    return manim_code, scene_class

def save_manim_code_to_temp_file(manim_code):
    temp_file_path = os.path.join(
        tempfile.gettempdir(), "generated_manim_code.py"
    )
    with open(temp_file_path, "w") as file:
        file.write(manim_code)
    print(f"Generated Manim code saved to {temp_file_path}")
    return temp_file_path

def run_manim(file_path, scene_class):
    command = ["manim", "-pql", file_path, scene_class]
    try:
        print("Running command:", " ".join(command))
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=120)
        print("✅ Manim command finished.\n--- Output ---")
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print("❌ Error running Manim:\n", e.stderr)
    except subprocess.TimeoutExpired:
        print("❌ Manim command timed out.")

# Speech Recognition Loop
recognizer = sr.Recognizer()
while True:
    with sr.Microphone() as source:
        print("Listening for commands...")
        audio = recognizer.listen(source, timeout=None, phrase_time_limit=10)
        try:
            speech_text = recognizer.recognize_google(audio)
            print(f"Recognized: {speech_text}")
            if not process_speech(speech_text):
                break
        except sr.UnknownValueError:
            print("❌ Could not understand the audio.")
        except sr.RequestError:
            print("❌ Speech recognition service is unavailable.")
        except KeyboardInterrupt:
            print("🛑 Program terminated by user.")
            break
