let socket = null;
let transcriptionEnabled = false;

// Handle messages from popup.js
chrome.runtime.onMessage.addListener((message) => {
  if (message.action === "startTranscription") {
    console.log("Starting transcription...");
    startWebSocket();
  } else if (message.action === "stopTranscription") {
    console.log("Stopping transcription...");
    stopWebSocket();
  } else if (message.action === "sendAudioChunk") {
    if (socket && socket.readyState === WebSocket.OPEN) {
      console.log("Sending audio chunk to WebSocket server...");
      socket.send(message.data);
    } else {
      console.error("WebSocket is not open. Cannot send audio chunk.");
    }
  }
});

// Start WebSocket connection
function startWebSocket() {
  if (transcriptionEnabled) {
    console.warn("WebSocket is already open. Skipping...");
    return;
  }

  console.log("Opening WebSocket connection...");
  socket = new WebSocket("ws://3.141.7.60:5000/transcribe");

  socket.onopen = () => {
    transcriptionEnabled = true;
    console.log("WebSocket connection established.");
  };

  socket.onmessage = (event) => {
    const transcription = event.data;
    console.log("Received transcription:", transcription);
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs.length > 0) {
        chrome.tabs.sendMessage(tabs[0].id, {
          action: "updateCaption",
          text: transcription,
        });
      }
    });
  };

  socket.onerror = (error) => {
    console.error("WebSocket error:", error);
  };

  socket.onclose = () => {
    transcriptionEnabled = false;
    console.log("WebSocket connection closed.");
  };
}

// Stop WebSocket connection
function stopWebSocket() {
  if (!transcriptionEnabled) {
    console.warn("WebSocket is already closed. Skipping...");
    return;
  }

  console.log("Closing WebSocket connection...");
  if (socket) {
    socket.close();
    socket = null;
  }

  transcriptionEnabled = false;
  console.log("WebSocket connection closed.");
}
