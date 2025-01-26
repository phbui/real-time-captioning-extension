let socket = null;
let transcriptionEnabled = false;
let mediaRecorder = null;
let capturedStream = null;

chrome.runtime.onMessage.addListener(async (message, sender) => {
  console.log("Background received message:", message);

  if (message.action === "stopTranscription") {
    console.log("Popup requested stopTranscription...");
    stopTranscription();
  } else if (message.action === "startCaptureFromContent") {
    console.log("Content script requested capture for tab:", sender.tab.id);
    console.log("Working with tab: ", sender.tab);
    startTranscriptionForTab(sender.tab.id);
  }
});

// Start transcription for a specific tab (e.g., content script call)
async function startTranscriptionForTab(tabId) {
  if (transcriptionEnabled) {
    console.warn("Transcription is already enabled.");
    return;
  }
  transcriptionEnabled = true;

  startWebSocket();
  try {
    console.log("Using tab for capture:", tabId);
    await startCaptureForTab(tabId);
  } catch (err) {
    console.error("Error capturing for tab:", err);
    stopTranscription();
  }
}

// Common logic to capture from a specific tabId
function startCaptureForTab(tabId) {
  return new Promise((resolve, reject) => {
    invokeTab(tabId)
      .then(() => {
        chrome.tabCapture.getMediaStreamId(
          { consumerTabId: tabId },
          async (mediaStreamId) => {
            if (chrome.runtime.lastError) {
              console.error(
                "getMediaStreamId error:",
                chrome.runtime.lastError.message
              );
              stopTranscription();
              reject(chrome.runtime.lastError);
              return;
            }
            if (!mediaStreamId) {
              console.error("Failed to get MediaStream ID.");
              stopTranscription();
              reject(new Error("No MediaStream ID."));
              return;
            }
            console.log("MediaStream ID:", mediaStreamId);

            try {
              capturedStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                  mandatory: {
                    chromeMediaSource: "tab",
                    chromeMediaSourceId: mediaStreamId,
                  },
                },
              });
              console.log(
                "Audio stream captured successfully:",
                capturedStream
              );

              mediaRecorder = new MediaRecorder(capturedStream);
              mediaRecorder.ondataavailable = (e) => {
                if (socket && socket.readyState === WebSocket.OPEN) {
                  console.log("Sending audio chunk to WebSocket server...");
                  socket.send(e.data);
                }
              };
              mediaRecorder.start(200); // send chunks every 200ms
              console.log("MediaRecorder started for tab:", tabId);
              resolve();
            } catch (err) {
              console.error("getUserMedia error:", err);
              stopTranscription();
              reject(err);
            }
          }
        );
      })
      .catch((err) => reject(err));
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

// "Invoke" the tab to satisfy user gesture constraints
function invokeTab(tabId) {
  return new Promise((resolve, reject) => {
    chrome.scripting.executeScript(
      {
        target: { tabId },
        func: () => console.log("Extension invoked for this page."),
      },
      () => {
        if (chrome.runtime.lastError) {
          console.error(
            "Failed to invoke tab:",
            chrome.runtime.lastError.message
          );
          reject(chrome.runtime.lastError);
          return;
        }
        console.log("Tab invoked successfully:", tabId);
        resolve();
      }
    );
  });
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
