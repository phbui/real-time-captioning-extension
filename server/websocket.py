import asyncio
import websockets
import pyaudio
import numpy as np
import whisper
import torch
import threading
import webrtcvad
import logging
from datetime import datetime, timedelta
import torch.backends.cudnn as cudnn
cudnn.benchmark = True

# Whisper model initialization (uses GPU if available)
model = whisper.load_model("turbo", device="cuda" if torch.cuda.is_available() else "cpu")


# Audio configuration
WHISPER_SAMPLE_RATE = 16000  # Whisper expects 16kHz
CHANNELS = 1  # Mono audio
FORMAT = pyaudio.paInt16  # 16-bit PCM
PHRASE_TIMEOUT = 0.4  # Seconds of silence to consider as a new phrase

# Voice Activity Detector
vad = webrtcvad.Vad()
vad.set_mode(2)  # Moderate aggressiveness

# Global buffers
audio_buffer = bytearray()  # For transcription
buffer_lock = threading.Lock()
phrase_time = None

# Global variables for managing the transcription task
current_task = None
task_lock = threading.Lock()

def preprocess_audio(raw_data, sample_rate=WHISPER_SAMPLE_RATE):
    max_samples = 30 * sample_rate  # 30 seconds of audio
    samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32)
    samples = samples / 32768.0  # Normalize to [-1.0, 1.0]

    # Pad with silence if shorter than 30 seconds
    if len(samples) < max_samples:
        padded_samples = np.zeros(max_samples, dtype=np.float32)
        padded_samples[:len(samples)] = samples
        return padded_samples
    else:
        return samples[:max_samples]  # Truncate if longer


async def transcribe_audio(raw_data):
    """Run Whisper transcription on the provided raw data."""
    try:
        audio_tensor = preprocess_audio(raw_data)

        # Move to GPU for processing
        audio_tensor = torch.from_numpy(audio_tensor).to("cuda", non_blocking=True)

        # Run Whisper transcription
        result = model.transcribe(
            audio_tensor,
            fp16=True,
            logprob_threshold=-1.0,
            no_speech_threshold=2.0,
            hallucination_silence_threshold=1.0,
            compression_ratio_threshold=1.0,
            language="en",
            suppress_tokens=""  # Adjusted to reduce hallucinations
        )
        text = result["text"].strip()
        return text

    except Exception as e:
        logging.error(f"Error in transcription: {e}")
        return ""
    
def is_speech(audio_chunk, sample_rate):
    """Check if the audio chunk contains speech using WebRTC VAD."""
    try:
        # Validate audio size (WebRTC VAD requires 10ms, 20ms, or 30ms frame size)
        frame_duration_ms = (len(audio_chunk) / (sample_rate / 1000))
        if frame_duration_ms not in [10, 20, 30]:
            raise ValueError(f"Invalid frame size: {frame_duration_ms}ms. Expected 10ms, 20ms, or 30ms.")
        
        return vad.is_speech(audio_chunk, sample_rate)
    except Exception as e:
        print(f"Error in is_speech: {e}")
        return False  # Return False as a fallback


async def handle_connection(websocket):
    global phrase_time
    try:
        async for message in websocket:
            if isinstance(message, bytes):  # Check if the message contains PCM audio data
                if is_speech(message, sample_rate=WHISPER_SAMPLE_RATE): 
                    with buffer_lock:
                        audio_buffer.extend(message)  # Add to the audio buffer for transcription
                    phrase_time = datetime.utcnow() 
            else:
                print("Received text:", message)
    except websockets.ConnectionClosed:
        print("Client disconnected.")
    except Exception as e:
        print(f"Error in connection: {e}")

async def main():
    print("Starting WebSocket server at ws://localhost:8765")
    # Start the transcription loop as an async task
    asyncio.create_task(transcribe_loop())

    # Start the WebSocket server
    async with websockets.serve(handle_connection, "localhost", 8765):
        await asyncio.Future()  # run forever


async def transcribe_loop():
    """
    Periodically reads the global audio buffer, processes it, and transcribes it using Whisper.
    """
    logging.info("Starting transcription loop...")
    transcription = [""]  # Initialize transcription list
    global current_task

    while True:
        now = datetime.utcnow()
        phrase_complete = False

        # Check if enough time has passed since the last detected speech
        if phrase_time and now - phrase_time > timedelta(seconds=PHRASE_TIMEOUT):
            phrase_complete = True

        # Safely extract audio data from the buffer
        async with asyncio.Lock():  # Use asyncio.Lock for async code
            raw_data = bytes(audio_buffer)
            if len(audio_buffer) == 0:
                await asyncio.sleep(0.1)
                continue

            if phrase_complete:
                audio_buffer.clear()

        # Cancel any ongoing transcription if new data arrives
        if current_task:
            current_task.cancel()

        # Start a new transcription task
        async def process_and_print():
            text = await transcribe_audio(raw_data)

            if (phrase_complete):
                transcription.append(text)
            else:
                transcription[-1] = text  # Update the current line

            print("[Transcription]")
            print(" ".join(transcription), end="\n")

        current_task = asyncio.create_task(process_and_print())

        await asyncio.sleep(0.1)  # Prevent excessive CPU usage

if __name__ == "__main__":
    asyncio.run(main())
