chrome.runtime.onMessage.addListener(async (message) => {
  if (message.target === "offscreen") {
    switch (message.type) {
      case "start-recording":
        startRecording(message.data);
        break;
      default:
        throw new Error("Unrecognized message:", message.type);
    }
  }
});

let socket = null;
let audioCtx = null;
let audioWorkletNode = null;
let sourceNode = null;

async function startRecording(streamId) {
  // If we already have a context, skip
  if (audioCtx) {
    console.warn("Recording is already in progress.");
    return;
  }

  // 1) Start WebSocket
  startWebSocket();

  // 2) Capture tab audio
  const mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      mandatory: {
        chromeMediaSource: "tab",
        chromeMediaSourceId: streamId,
      },
    },
  });

  const inputSampleRate = 48000;

  // 3) Create AudioContext and load our AudioWorklet module
  audioCtx = new AudioContext({ sampleRate: inputSampleRate });
  console.log("Sample rate:", audioCtx.sampleRate);

  await audioCtx.audioWorklet.addModule(
    chrome.runtime.getURL("offscreen/pcm-worklet.js")
  );

  // 4) Create a MediaStream source from the captured stream
  sourceNode = audioCtx.createMediaStreamSource(mediaStream);

  // 5) Create the AudioWorkletNode using the processor name we’ll define below
  audioWorkletNode = new AudioWorkletNode(audioCtx, "pcm-worklet-processor", {
    numberOfInputs: 1, // 1 input from the media stream
    numberOfOutputs: 1, // 1 output to the user
    outputChannelCount: [2], // Stereo output
    processorOptions: {
      inputSampleRate,
    },
  });

  // 6) Listen for audio data messages from the AudioWorkletProcessor
  audioWorkletNode.port.onmessage = (event) => {
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    const floatSamples = event.data; // Mono samples received
    const int16Samples = convertFloat32ToInt16(floatSamples);
    socket.send(int16Samples);
  };

  // 7) Connect the graph: source -> worklet -> destination
  //    This lets the user hear the tab audio while also extracting PCM.
  sourceNode.connect(audioWorkletNode);
  audioWorkletNode.connect(audioCtx.destination);

  // Update URL hash to note we’re “recording”
  window.location.hash = "recording";
}

function convertFloat32ToInt16(float32Array) {
  const len = float32Array.length;
  const int16Buffer = new Int16Array(len);
  for (let i = 0; i < len; i++) {
    let s = Math.max(-1, Math.min(1, float32Array[i]));
    int16Buffer[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return int16Buffer;
}

function startWebSocket() {
  if (socket && socket.readyState === WebSocket.OPEN) {
    console.warn("WebSocket is already open.");
    return;
  }

  console.log("Opening WebSocket connection...");
  socket = new WebSocket("ws://localhost:8765");

  socket.onopen = () => console.log("WebSocket connection established.");
  socket.onerror = (err) => console.error("WebSocket error:", err);
  socket.onclose = () => {
    console.log("WebSocket connection closed.");
    socket = null;
  };
}
