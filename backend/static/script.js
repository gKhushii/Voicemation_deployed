const recordBtn = document.getElementById("recordBtn");
const videoElement = document.getElementById("outputVideo");
const subtitleDisplay = document.getElementById("subtitleDisplay");
const currentSubtitleText = document.getElementById("currentSubtitleText");
const statusElement = document.getElementById("status");

const aiDurationBtn = document.getElementById("aiDurationBtn");
const manualDurationToggle = document.getElementById("manualDurationToggle");
const manualDurationSelect = document.getElementById("manualDurationSelect");
const durationHint = document.querySelector(".duration-hint");

let mediaRecorder;
let audioChunks = [];
let subtitleData = [];
let currentDurationSetting = 'ai'; // 'ai' or 'manual'

// Backend API URL
const BACKEND_URL = "http://127.0.0.1:5001";  // ⬅️ IMPORTANT

// ------------------------
// Duration Control
// ------------------------
function updateDurationSetting(setting) {
    aiDurationBtn.classList.remove('active');
    manualDurationToggle.classList.remove('active');

    if (setting === 'ai') {
        currentDurationSetting = 'ai';
        aiDurationBtn.classList.add('active');
        manualDurationSelect.style.display = 'none';
        manualDurationSelect.disabled = true;
        durationHint.innerText = "Current Setting: AI will determine the optimal duration based on the content.";
    } else {
        currentDurationSetting = 'manual';
        manualDurationToggle.classList.add('active');
        manualDurationSelect.style.display = 'inline-block';
        manualDurationSelect.disabled = false;
        durationHint.innerText = `Current Setting: Video length is manually capped at ${manualDurationSelect.value} seconds.`;
    }
}

aiDurationBtn.addEventListener('click', () => updateDurationSetting('ai'));
manualDurationToggle.addEventListener('click', () => updateDurationSetting('manual'));
manualDurationSelect.addEventListener('change', () => {
    if (currentDurationSetting === 'manual') {
        durationHint.innerText = `Current Setting: Video length is manually capped at ${manualDurationSelect.value} seconds.`;
    }
});

// Initialize with AI mode active
updateDurationSetting('ai');

// ------------------------
// Subtitle Rendering
// ------------------------
function renderAllSubtitles(subtitles) {
    if (!subtitles || !subtitles.length) {
        currentSubtitleText.textContent = "No subtitles available.";
        return;
    }

    let paragraphs = [];
    let currentParagraph = [];

    const SCENE_BREAK = 10;

    subtitles.forEach((sub, idx) => {
        currentParagraph.push(sub.text);
        if ((idx + 1) % SCENE_BREAK === 0) {
            paragraphs.push(currentParagraph.join(' '));
            currentParagraph = [];
        }
    });

    if (currentParagraph.length) paragraphs.push(currentParagraph.join(' '));

    currentSubtitleText.innerHTML = paragraphs
        .map(p => `<p>${p}</p>`)
        .join('');

    subtitleDisplay.scrollTop = 0;
}

// ------------------------
// Recording + Generation
// ------------------------
recordBtn.addEventListener("click", async () => {
    if (!mediaRecorder || mediaRecorder.state === "inactive") {

        audioChunks = [];
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
        } catch (error) {
            statusElement.innerText = "❌ Error: Could not access microphone. Check permissions.";
            return;
        }

        mediaRecorder.ondataavailable = e => audioChunks.push(e.data);

        mediaRecorder.onstop = async () => {
            recordBtn.disabled = true;

            const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
            const formData = new FormData();
            formData.append("audio", audioBlob, "speech.webm");

            const durationValue =
                currentDurationSetting === "manual"
                    ? manualDurationSelect.value
                    : "0";

            formData.append("duration_limit", durationValue);

            statusElement.innerText = "⏳ Generating...";

            try {
                const response = await fetch(`${BACKEND_URL}/generate_audio`, {
                    method: "POST",
                    body: formData,
                    // ⬇️ Tell Flask we want JSON so the global error handler returns JSON instead of HTML
                    headers: {
                        "Accept": "application/json"
                    }
                });

                let result;
                const contentType = response.headers.get("content-type") || "";
                console.log("Response status:", response.status);
                console.log("Response content-type:", contentType);

                if (!response.ok) {
                    // Try to read body for better diagnostics (could be JSON or HTML)
                    const bodyText = await response.text();
                    console.error("Non-OK response body:", bodyText);
                    throw new Error(`Server returned ${response.status}: ${bodyText.slice(0, 200)}`);
                }

                if (contentType.includes("application/json")) {
                    result = await response.json();
                } else {
                    // Not JSON — read body and show a clearer error message
                    const bodyText = await response.text();
                    console.error("Expected JSON but got:", bodyText);
                    throw new Error(
                        `Expected JSON but server returned '${contentType}': ${bodyText.slice(0, 200)}`
                    );
                }

                if (result.video_url) {
                    subtitleData = result.subtitles_json || [];
                    videoElement.src = `${BACKEND_URL}${result.video_url}?t=${Date.now()}`;
                    videoElement.load();
                    videoElement.style.display = "block";

                    renderAllSubtitles(subtitleData);
                    statusElement.innerText = "✅ Animation generated!";

                    await videoElement.play().catch(() => {});
                } else {
                    statusElement.innerText = `❌ Error: ${result.error || "Unknown error"}`;
                    videoElement.style.display = "none";
                }

            } catch (err) {
                console.error("Fetch / processing error:", err);
                statusElement.innerText = `🚫 Network or server error: ${err.message}`;
                videoElement.style.display = "none";
            } finally {
                recordBtn.disabled = false;
            }
        };

        mediaRecorder.start();
        recordBtn.innerText = "⏹ Stop Recording";
        statusElement.innerText = "🔴 Recording...";
    } else {
        mediaRecorder.stop();
        recordBtn.innerText = "🎤 Record & Generate Animation";
    }
});
