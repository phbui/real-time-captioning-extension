let socket = null;
let transcriptionEnabled = false;

// Handle messages from popup.js
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "startTranscription") {
    startTranscription();
  } else if (message.action === "stopTranscription") {
    stopTranscription();
  }
});

// Start WebSocket connection
function startTranscription() {
  if (transcriptionEnabled) return;

  socket = new WebSocket("ws://3.141.7.60:5000/transcribe");

  socket.onopen = () => {
    transcriptionEnabled = true;
    console.log("WebSocket connection opened.");
  };

  socket.onmessage = (event) => {
    const transcription = event.data;
    console.log("Received transcription:", transcription);

    // Send transcription to captions.js
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      chrome.tabs.sendMessage(tabs[0].id, {
        action: "updateCaption",
        text: transcription,
      });
    });
  };

  socket.onerror = (error) => {
    console.error("WebSocket error:", error);
  };

  socket.onclose = () => {
    console.log("WebSocket connection closed.");
    transcriptionEnabled = false;
  };
}

// Stop WebSocket connection
function stopTranscription() {
  if (!transcriptionEnabled || !socket) return;

  socket.close();
  socket = null;
  transcriptionEnabled = false;
  console.log("Transcription stopped.");
}
