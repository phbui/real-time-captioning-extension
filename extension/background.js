let socket = null;
let isTranscribing = false;
let transcriptionEnabled = false;
let activeTabId = null;

// Handle extension button clicks
chrome.action.onClicked.addListener((tab) => {
  console.log("Extension button clicked:", tab);

  activeTabId = tab.id;

  if (!isTranscribing) {
    console.log("Starting transcription...");
    startTranscription(tab);
  } else {
    console.log("Stopping transcription...");
    stopTranscription(tab.id);
  }
  isTranscribing = !isTranscribing;
});

// Central listener for runtime messages
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.action) {
    case "audioChunk":
      handleAudioChunk(message.data);
      sendResponse({ success: true });
      break;

    case "stopMediacapture":
      console.log("Stopping media capture on content script...");
      sendResponse({ success: true });
      break;

    default:
      console.warn("Unknown message action:", message.action);
      break;
  }
  return true; // Indicates asynchronous response
});

// Handle tab and window focus changes to reset transcription state
chrome.tabs.onActivated.addListener(resetTranscriptionState);
chrome.windows.onFocusChanged.addListener((windowId) => {
  if (windowId !== chrome.windows.WINDOW_ID_NONE) {
    resetTranscriptionState();
  }
});

// Reset transcription state
function resetTranscriptionState() {
  if (isTranscribing) {
    console.log("Resetting transcription state...");
    stopTranscription(activeTabId);
    isTranscribing = false;
  }
}

// Start transcription for the active tab
function startTranscription(tab) {
  chrome.action.setIcon({ path: "assets/mic_enabled.png" });
  chrome.action.setTitle({ title: "Disable transcription" });

  startWebSocket();

  // Start capturing audio from the specified tab
  startCaptureForTab(tab.id)
    .then(() => console.log("Transcription started successfully."))
    .catch((err) => {
      console.error("Failed to start transcription:", err);
      stopTranscription(tab.id);
    });
}

// Stop transcription for the active tab
function stopTranscription(tabId) {
  chrome.action.setIcon({ path: "assets/mic_disabled.png" });
  chrome.action.setTitle({ title: "Enable transcription" });

  stopWebSocket();

  chrome.tabs.sendMessage(tabId, { action: "stopMediacapture" }, (response) => {
    if (chrome.runtime.lastError) {
      console.warn(
        "Error stopping media capture:",
        chrome.runtime.lastError.message
      );
    } else {
      console.log("Media capture stopped:", response);
    }
  });

  console.log("Transcription fully stopped.");
}

// Start capturing audio from the specified tab
function startCaptureForTab(tabId) {
  return new Promise((resolve, reject) => {
    console.log("Starting capture for tab:", tabId);

    chrome.tabCapture.getMediaStreamId(
      { consumerTabId: tabId },
      (mediaStreamId) => {
        if (chrome.runtime.lastError || !mediaStreamId) {
          reject(
            new Error(
              chrome.runtime.lastError?.message ||
                "Failed to get MediaStream ID."
            )
          );
          return;
        }

        console.log("MediaStream ID retrieved:", mediaStreamId);

        chrome.tabs.sendMessage(
          tabId,
          { action: "startMediaCapture", mediaStreamId },
          (response) => {
            if (chrome.runtime.lastError || !response?.success) {
              reject(
                new Error(chrome.runtime.lastError?.message || response?.error)
              );
            } else {
              resolve();
            }
          }
        );
      }
    );
  });
}

// Handle audio chunks from the content script
function handleAudioChunk(data) {
  const blob = new Blob([data], { type: "audio/webm" });
  console.log("Received audio chunk from content script:", blob);

  if (socket && socket.readyState === WebSocket.OPEN) {
    console.log("Sending audio chunk to WebSocket...");
    socket.send(blob);
  }
}

// WebSocket handling
function startWebSocket() {
  if (socket && socket.readyState === WebSocket.OPEN) {
    console.warn("WebSocket is already open.");
    return;
  }

  console.log("Opening WebSocket connection...");
  socket = new WebSocket("ws://3.141.7.60:5000/transcribe");

  socket.onopen = () => console.log("WebSocket connection established.");
  socket.onerror = (err) => console.error("WebSocket error:", err);
  socket.onmessage = (event) => {
    console.log("Received transcription:", event.data);
    updateCaption(event.data);
  };
  socket.onclose = () => {
    console.log("WebSocket connection closed.");
    socket = null;
  };
}

function stopWebSocket() {
  if (socket) {
    console.log("Closing WebSocket connection...");
    socket.close();
    socket = null;
  }
}

// Update captions on the active tab
function updateCaption(text) {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs[0]) {
      chrome.tabs.sendMessage(tabs[0].id, {
        action: "updateCaption",
        text,
      });
    }
  });
}
