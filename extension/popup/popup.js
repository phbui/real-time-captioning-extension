const toggleButton = document.getElementById("toggleBtn");
const status = document.getElementById("status");

// Restore button state from storage
chrome.storage.local.get(["transcriptionEnabled"], (result) => {
  const enabled = result.transcriptionEnabled ?? false;
  if (result.transcriptionEnabled === undefined) {
    chrome.storage.local.set({ transcriptionEnabled: false });
  }
  updateUI(enabled);
});

// Update UI based on the state
function updateUI(enabled) {
  toggleButton.textContent = enabled
    ? "Disable Captioning"
    : "Enable Captioning";
  status.textContent = enabled ? "Listening..." : "Captioning is disabled.";
  status.style.color = enabled ? "green" : "red";
}

// Toggle transcription state
toggleButton.addEventListener("click", () => {
  chrome.storage.local.get(["transcriptionEnabled"], (result) => {
    const transcriptionEnabled = !result.transcriptionEnabled;

    if (transcriptionEnabled) captureTabAudio();

    chrome.storage.local.set({ transcriptionEnabled });
    updateUI(transcriptionEnabled);

    chrome.runtime.sendMessage({
      action: transcriptionEnabled ? "startTranscription" : "stopTranscription",
    });
  });
});

// Capture audio from the active tab
function captureTabAudio() {
  console.log("Attempting to capture audio from the active tab...");
  chrome.tabCapture.capture({ audio: true, video: false }, (stream) => {
    print(stream);

    if (!stream) {
      console.error("Failed to capture tab audio.");
      return;
    }
    console.log("Audio stream captured successfully.");

    // Keep audio playing while capturing
    const context = new AudioContext();
    const newStream = context.createMediaStreamSource(stream);
    newStream.connect(context.destination);

    const recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (event) => {
      chrome.runtime.sendMessage({
        action: "sendAudioChunk",
        data: event.data,
      });
    };
    recorder.start(200); // Record audio in chunks of 200ms
    console.log("MediaRecorder started.");
  });
}
