let isTranscribing = false;

function injectButtonStyles() {
  if (document.getElementById("transcription-btn-style")) return; // Avoid injecting multiple times.

  const style = document.createElement("style");
  style.id = "transcription-btn-style"; // Unique ID for the style tag.
  style.textContent = `
    #transcription-btn {
      position: absolute;
      margin-left: -50px;
      display: flex;
      align-items: center;
      justify-content: center;
      width: 50px;
      height: 50px;
    }

    #transcription-btn img {
      width: 24px;
      height: 24px;
    }
  `;
  document.head.appendChild(style);
}

function addTranscriptionButton() {
  // If the button already exists, do nothing.
  if (document.getElementById("transcription-btn")) {
    return;
  }

  injectButtonStyles();

  // Find the right-side YouTube control bar.
  const rightControls = document.querySelector(".ytp-right-controls");
  if (!rightControls) {
    return; // It's possible the player hasn't loaded yet.
  }

  // Create a new button styled like YouTube's buttons.
  const button = document.createElement("button");
  button.id = "transcription-btn";
  button.classList.add("ytp-button"); // Helps match YouTube styling
  button.title = "Enable transcription"; // Tooltip text

  // Add an image for the icon
  const icon = document.createElement("img");
  icon.src = chrome.runtime.getURL("assets/mic_disabled.svg"); // Default to disabled icon
  icon.alt = "Microphone Icon";
  icon.style.width = "24px";
  icon.style.height = "24px";

  button.appendChild(icon);

  // When the button is clicked, toggle start/stop transcription and update the icon.
  button.addEventListener("click", () => {
    if (!isTranscribing) {
      console.log("Starting transcription...");
      chrome.runtime.sendMessage({ action: "startCaptureFromContent" });
      icon.src = chrome.runtime.getURL("assets/mic_enabled.svg"); // Change to enabled icon
      button.title = "Disable transcription";
    } else {
      console.log("Stopping transcription...");
      chrome.runtime.sendMessage({ action: "stopTranscription" });
      icon.src = chrome.runtime.getURL("assets/mic_disabled.svg"); // Change to disabled icon
      button.title = "Enable transcription";
    }

    isTranscribing = !isTranscribing;
  });

  // Insert the new button at the beginning of the right controls.
  rightControls.insertBefore(button, rightControls.firstChild);
}

// Continuously check if YouTube’s player controls are loaded,
// and if the button hasn't been inserted yet.
const buttonInterval = setInterval(addTranscriptionButton, 1000);
