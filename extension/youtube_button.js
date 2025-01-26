let isTranscribing = false;

function addTranscriptionButton() {
  // If the button already exists, do nothing.
  if (document.getElementById("transcription-btn")) {
    return;
  }

  // Find the right-side YouTube control bar.
  const rightControls = document.querySelector(".ytp-right-controls");
  if (!rightControls) {
    return; // It's possible the player hasn't loaded yet.
  }

  // Create a new button that looks (roughly) like the other YT player buttons.
  const button = document.createElement("button");
  button.id = "transcription-btn";
  button.classList.add("ytp-button"); // helps match YouTube styling
  button.style.color = "white";
  button.innerText = "Transcribe";

  // When the button is clicked, toggle start/stop transcription.
  button.addEventListener("click", () => {
    if (!isTranscribing) {
      console.log("Starting transcription...");
      chrome.runtime.sendMessage({ action: "startCaptureFromContent" });
      button.innerText = "Stop Transcribing";
    } else {
      console.log("Stopping transcription...");
      chrome.runtime.sendMessage({ action: "stopTranscription" });
      button.innerText = "Transcribe";
    }

    isTranscribing = !isTranscribing;
  });

  // Insert the new button at the beginning of the right controls.
  rightControls.insertBefore(button, rightControls.firstChild);
}

// Continuously check if YouTube’s player controls are loaded,
// and if the button hasn't been inserted yet.
const buttonInterval = setInterval(addTranscriptionButton, 1000);
