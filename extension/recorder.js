let mediaRecorder = null;
let audioStream = null;
let isCapturing = false;
let audioElement = null;

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "startMediaCapture") {
    if (isCapturing) {
      console.warn("Media capture is already running.");
      sendResponse({ success: false, error: "Media capture already running." });
      return;
    }

    console.log("Starting media capture...");

    navigator.mediaDevices
      .getUserMedia({
        audio: {
          mandatory: {
            chromeMediaSource: "tab",
            chromeMediaSourceId: message.mediaStreamId,
          },
        },
      })
      .then((stream) => {
        console.log("Audio stream captured successfully:", stream);

        const audioTracks = stream.getAudioTracks();
        console.log("Audio tracks in stream:", audioTracks);
        audioTracks.forEach((track) => {
          console.log(
            "Track enabled:",
            track.enabled,
            "Track readyState:",
            track.readyState
          );
        });

        // Play audio via <audio> element
        if (!audioElement) {
          audioElement = document.createElement("audio");
          audioElement.controls = false;
          audioElement.style.display = "none";
          document.body.appendChild(audioElement);
        }
        audioElement.srcObject = stream;
        audioElement.autoplay = true;
        audioElement.muted = false;
        audioElement.volume = 1.0;

        audioElement.addEventListener("play", () => {
          console.log("Audio element started playing.");
        });
        audioElement.addEventListener("error", (e) => {
          console.error("Audio playback error:", e);
        });

        // Optional: Route audio through AudioContext
        const audioContext = new AudioContext();
        const audioSource = audioContext.createMediaStreamSource(stream);
        audioSource.connect(audioContext.destination);
        audioContext.resume().then(() => {
          console.log("AudioContext resumed and audio routed.");
        });

        // Save stream and setup MediaRecorder
        audioStream = stream;
        mediaRecorder = new MediaRecorder(stream);
        mediaRecorder.ondataavailable = async (e) => {
          if (isCapturing) {
            const arrayBuffer = await e.data.arrayBuffer();
            chrome.runtime.sendMessage({
              action: "audioChunk",
              data: arrayBuffer,
            });
          }
        };

        mediaRecorder.start(200);
        console.log("MediaRecorder started.");
        isCapturing = true;
        sendResponse({ success: true });
      })
      .catch((err) => {
        console.error("Error capturing audio stream:", err);
        sendResponse({ success: false, error: err.message });
      });

    return true;
  }

  if (message.action === "stopMediaCapture") {
    console.log("Stopping media capture...");

    if (!isCapturing) {
      console.warn("Media capture is not running.");
      sendResponse({ success: false, error: "No media capture to stop." });
      return;
    }

    if (mediaRecorder) {
      mediaRecorder.stop();
      mediaRecorder = null;
      console.log("MediaRecorder stopped.");
    }

    if (audioStream) {
      audioStream.getTracks().forEach((track) => track.stop());
      audioStream = null;
      console.log("Audio stream stopped.");
    }

    if (audioElement) {
      audioElement.srcObject = null;
      audioElement.remove();
      audioElement = null;
      console.log("Audio playback stopped.");
    }

    isCapturing = false;
    sendResponse({ success: true });
    return true;
  }
});
