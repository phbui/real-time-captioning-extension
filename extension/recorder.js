chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "startMediaCapture") {
    console.log("Starting media capture...");

    navigator.mediaDevices
      .getUserMedia({
        audio: {
          mandatory: {
            chromeMediaSource: "tab",
            chromeMediaSourceId: message.mediaStreamId, // Pass the mediaStreamId
          },
        },
      })
      .then((stream) => {
        console.log("Audio stream captured successfully:", stream);

        const output = new AudioContext();
        const source = output.createMediaStreamSource(stream);
        source.connect(output.destination);

        // Set up MediaRecorder for capturing the audio
        const mediaRecorder = new MediaRecorder(stream);
        mediaRecorder.ondataavailable = async (e) => {
          // Send audio chunks to the background script for WebSocket streaming
          const arrayBuffer = await e.data.arrayBuffer();

          // Send the ArrayBuffer to background.js
          chrome.runtime.sendMessage({
            action: "audioChunk",
            data: arrayBuffer,
          });
        };

        mediaRecorder.start(200); // Record in 200ms chunks
        console.log("MediaRecorder started.");
        sendResponse({ success: true });
      })
      .catch((err) => {
        console.error("Error capturing audio stream:", err);
        sendResponse({ success: false, error: err.message });
      });

    // Indicate that the response will be asynchronous
    return true;
  }
});
