let socket = null;
let transcriptionEnabled = false;
let mediaRecorder = null;
let capturedStream = null;
let enableTranscription = false;
let currentTab = null;
let activeTabId = null;

chrome.action.onClicked.addListener((tab) => {
  console.log("Extension button clicked:", tab);

  activeTabId = tab.id; // Update the active tab ID.

  if (!isTranscribing) {
    console.log("Starting transcription...");
    chrome.runtime.sendMessage({
      action: "startCaptureFromContent",
      tabId: tab.id,
    });
    chrome.action.setIcon({ path: "assets/mic_enabled.png" }); // Show enabled icon.
    chrome.action.setTitle({ title: "Disable transcription" }); // Update tooltip.
    startTranscriptionForTab(tab);
  } else {
    console.log("Stopping transcription...");
    chrome.runtime.sendMessage({ action: "stopTranscription", tabId: tab.id });
    chrome.action.setIcon({ path: "assets/mic_disabled.png" }); // Show disabled icon.
    chrome.action.setTitle({ title: "Enable transcription" }); // Update tooltip.
    stopTranscription();
  }

  isTranscribing = !isTranscribing; // Toggle transcription state.
});

// Listen for tab changes and reset transcription state.
chrome.tabs.onActivated.addListener((activeInfo) => {
  if (activeTabId !== activeInfo.tabId) {
    console.log("Tab changed:", activeInfo);
    resetTranscriptionState();
  }
});

// Listen for window focus changes and reset transcription state.
chrome.windows.onFocusChanged.addListener((windowId) => {
  if (windowId === chrome.windows.WINDOW_ID_NONE) {
    console.log("No focused window.");
    return; // Ignore if there's no active window.
  }
  resetTranscriptionState();
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "audioChunk") {
    console.log("Received audio chunk from content script:", message);

    // Forward the audio chunk to WebSocket if needed
    if (socket && socket.readyState === WebSocket.OPEN) {
      console.log("Sending audio chunk to WebSocket...");
      socket.send(message.data);
    }

    // Optionally send a response back to the content script
    sendResponse({ success: true });
  }

  // Ensure the listener does not break if it's asynchronous
  return true; // Keeps the messaging channel open for async responses
});

function resetTranscriptionState() {
  isTranscribing = false;
  chrome.action.setIcon({ path: "assets/mic_disabled.png" }); // Reset to disabled icon.
  chrome.action.setTitle({ title: "Enable transcription" }); // Reset tooltip.
  stopTranscription();
  console.log("Transcription state reset due to tab/window switch.");
}

// Start transcription for a specific tab (e.g., content script call)
async function startTranscriptionForTab(tab) {
  if (transcriptionEnabled) {
    console.warn("Transcription is already enabled.");
    return;
  }
  transcriptionEnabled = true;

  startWebSocket();
  try {
    console.log("Using tab for capture:", tab);
    const tabId = tab.id;
    await startCaptureForTab(tabId);
  } catch (err) {
    console.error("Error capturing for tab:", err);
    stopTranscription();
  }
}

// Common logic to capture from a specific tabId
function startCaptureForTab(tabId) {
  return new Promise((resolve, reject) => {
    console.log("Retrieving MediaStream ID for tab:", tabId);

    chrome.tabCapture.getMediaStreamId(
      { consumerTabId: tabId },
      (mediaStreamId) => {
        if (chrome.runtime.lastError || !mediaStreamId) {
          console.error(
            "getMediaStreamId error:",
            chrome.runtime.lastError?.message || "No MediaStream ID."
          );
          reject(
            new Error(
              chrome.runtime.lastError?.message ||
                "Failed to get MediaStream ID."
            )
          );
          return;
        }

        console.log("MediaStream ID retrieved:", mediaStreamId);

        // Send a message to the content script to start media capture
        chrome.tabs.sendMessage(
          tabId,
          { action: "startMediaCapture", mediaStreamId: mediaStreamId },
          (response) => {
            if (chrome.runtime.lastError || !response?.success) {
              console.error(
                "Content script failed to start capture:",
                chrome.runtime.lastError?.message || response?.error
              );
              reject(
                new Error(chrome.runtime.lastError?.message || response?.error)
              );
            } else {
              console.log(
                "Media capture started successfully in content script."
              );
              resolve();
            }
          }
        );
      }
    );
  });
}

function stopTranscription() {
  if (!transcriptionEnabled) {
    console.warn("Transcription already stopped.");
    return;
  }
  transcriptionEnabled = false;

  stopWebSocket();

  if (mediaRecorder) {
    console.log("Stopping MediaRecorder...");
    mediaRecorder.stop();
    mediaRecorder = null;
  }
  if (capturedStream) {
    capturedStream.getTracks().forEach((track) => track.stop());
    capturedStream = null;
  }
  console.log("Transcription fully stopped.");
}

// WebSocket handling
function startWebSocket() {
  if (socket && socket.readyState === WebSocket.OPEN) {
    console.warn("WebSocket is already open.");
    return;
  }
  console.log("Opening WebSocket connection...");
  socket = new WebSocket("ws://3.141.7.60:5000/transcribe");

  socket.onopen = () => {
    console.log("WebSocket connection established.");
  };
  socket.onerror = (err) => {
    console.error("WebSocket error:", err);
  };
  socket.onmessage = (event) => {
    console.log("Received transcription:", event.data);
    // Forward the transcription text to the currently active tab’s content script
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]) {
        chrome.tabs.sendMessage(tabs[0].id, {
          action: "updateCaption",
          text: event.data,
        });
      }
    });
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
