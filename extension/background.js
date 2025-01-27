chrome.action.onClicked.addListener(async (tab) => {
  console.log("Extension icon clicked. Tab info:", tab);

  const existingContexts = await chrome.runtime.getContexts({});
  console.log("Existing contexts:", existingContexts);

  let recording = false;

  const offscreenDocument = existingContexts.find(
    (c) => c.contextType === "OFFSCREEN_DOCUMENT"
  );
  console.log("Offscreen document found:", offscreenDocument);

  // If an offscreen document is not already open, create one.
  if (!offscreenDocument) {
    console.log("No offscreen document found. Creating a new one...");
    await chrome.offscreen.createDocument({
      url: "offscreen/offscreen.html",
      reasons: ["USER_MEDIA"],
      justification: "Recording from chrome.tabCapture API",
    });
    console.log("Offscreen document created.");
  } else {
    recording = offscreenDocument.documentUrl.endsWith("#recording");
    console.log(
      "Offscreen document already exists. Recording status:",
      recording
    );
  }

  // If recording is active, stop it
  if (recording) {
    console.log(
      "Recording is active. Sending stop message to offscreen document."
    );
    chrome.runtime.sendMessage({
      type: "stop-recording",
      target: "offscreen",
    });
    chrome.action.setIcon({ path: "assets/mic_disabled.png" });
    console.log("Icon updated to indicate recording stopped.");
    return;
  }

  console.log("Starting a new recording...");

  // Get a MediaStream for the active tab.
  let streamId;
  try {
    streamId = await chrome.tabCapture.getMediaStreamId({
      targetTabId: tab.id,
    });
    console.log("Media stream ID retrieved:", streamId);
  } catch (error) {
    console.error("Failed to get MediaStream ID:", error);
    return;
  }

  // Send the stream ID to the offscreen document to start recording.
  console.log(
    "Sending start-recording message to offscreen document with stream ID."
  );
  chrome.runtime.sendMessage({
    type: "start-recording",
    target: "offscreen",
    data: streamId,
  });

  chrome.action.setIcon({ path: "assets/mic_enabled.png" });
  console.log("Icon updated to indicate recording started.");
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.action) {
    case "audioChunk":
      handleAudioChunk(message.data);
      sendResponse({ success: true });
      break;

    default:
      console.warn("Unknown message action:", message.action);
      break;
  }
  return true; // Indicates asynchronous response
});

function handleAudioChunk(data) {
  const blob = new Blob([data], { type: "audio/webm" });
  console.log("Received audio chunk from content script:", blob);

  if (socket && socket.readyState === WebSocket.OPEN) {
    console.log("Sending audio chunk to WebSocket...");
    //socket.send(blob);
  }
}

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
