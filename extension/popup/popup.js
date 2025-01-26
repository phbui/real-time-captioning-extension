const toggleButton = document.getElementById("toggleBtn");
const status = document.getElementById("status");

// Restore button state from storage
chrome.storage.local.get(["transcriptionEnabled"], (result) => {
  const enabled = result.transcriptionEnabled || false;
  updateUI(enabled);
});

// Update button and status UI
function updateUI(enabled) {
  toggleButton.textContent = enabled
    ? "Disable Captioning"
    : "Enable Captioning";
  status.textContent = enabled ? "Listenning..." : "Captioning is disabled.";
  status.style.color = enabled ? "green" : "red";
}

// Toggle button click handler
toggleButton.addEventListener("click", () => {
  chrome.storage.local.get(["transcriptionEnabled"], (result) => {
    const transcriptionEnabled = !result.transcriptionEnabled;

    // Save state and update UI
    chrome.storage.local.set({ transcriptionEnabled });
    updateUI(transcriptionEnabled);

    // Send message to background.js
    chrome.runtime.sendMessage({
      action: transcriptionEnabled ? "startTranscription" : "stopTranscription",
    });
  });
});
