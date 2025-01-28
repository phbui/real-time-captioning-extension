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
# Whisper model initialization (uses GPU if available)
model = whisper.load_model("turbo", device="cuda" if torch.cuda.is_available() else "cpu")


# Audio configuration
INPUT_SAMPLE_RATE = 48000  # Microphone sample rate
WHISPER_SAMPLE_RATE = 16000  # Whisper expects 16kHz
CHANNELS = 1  # Mono audio
FORMAT = pyaudio.paInt16  # 16-bit PCM
CHUNK_SIZE = int(INPUT_SAMPLE_RATE * 0.02)  # 20ms frames
PHRASE_TIMEOUT = 0.5  # Seconds of silence to consider as a new phrase

# Voice Activity Detector
vad = webrtcvad.Vad()
vad.set_mode(2)  # Moderate aggressiveness

# Global buffers
audio_buffer = bytearray()  # For transcription
buffer_lock = threading.Lock()
phrase_time = None

def is_speech(audio_chunk, sample_rate):
    """Check if the audio chunk contains speech using WebRTC VAD."""
    if len(audio_chunk) < 0:  # 16-bit PCM = 2 bytes per sample
        raise ValueError("Audio chunk size does not match expected frame duration")
    return vad.is_speech(audio_chunk, sample_rate)

async def handle_connection(websocket):
    global phrase_time
    try:
        async for message in websocket:
            if isinstance(message, bytes):  # Check if the message contains PCM audio data
                with buffer_lock:
                    audio_buffer.extend(message)  # For transcription
                phrase_time = datetime.utcnow()  # Update the last time speech was detected
            else:
                print("Received text:", message)
    except websockets.ConnectionClosed:
        print("Client disconnected.")
    except Exception as e:
        print(f"Error: {e}")

async def main():
    print("Starting WebSocket server at ws://localhost:8765")
    # Launch a background thread that periodically transcribes
    threading.Thread(target=transcribe_loop, daemon=True).start()

    # Start the WebSocket server
    async with websockets.serve(handle_connection, "localhost", 8765):
        await asyncio.Future()  # run forever

def transcribe_loop():
    """
    Periodically reads the global audio buffer, processes it, and transcribes it using Whisper.
    """
    logging.info("Starting transcription loop...")
    transcription = [""]  # Initialize transcription list
    while True:

        now = datetime.utcnow()
        phrase_complete = False

        # Check if enough time has passed since the last detected speech
        if phrase_time and now - phrase_time > timedelta(seconds=PHRASE_TIMEOUT):
            phrase_complete = True

        # Safely extract audio data from the buffer
        with buffer_lock:
            if len(audio_buffer) == 0 or not phrase_complete:
                continue
            raw_data = bytes(audio_buffer)
            audio_buffer.clear()

        # Convert raw PCM data to float32 numpy array
        samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32)

        # Resample from 48kHz to 16kHz
        audio_tensor = torch.from_numpy(samples).float()
        audio_tensor_16k = torch.nn.functional.interpolate(
            audio_tensor.unsqueeze(0).unsqueeze(0),
            scale_factor=WHISPER_SAMPLE_RATE / INPUT_SAMPLE_RATE,
            mode='linear',
            align_corners=False
        ).squeeze().numpy() / 32768.0  # Normalize to [-1.0, 1.0]

        try:
            # Run Whisper transcription
            result = model.transcribe(
                audio_tensor_16k,
                fp16=True,
                logprob_threshold=-1.0,
                no_speech_threshold=2.0,
                hallucination_silence_threshold=1.0,
                compression_ratio_threshold=1.0,
                verbose=False,
                language="en",
                suppress_tokens=""  # Adjusted to reduce hallucinations
            )
            text = result["text"].strip()

            # Handle transcription updates
            if phrase_complete:
                transcription.append(text)  # Start a new transcription line
            else:
                transcription[-1] = text  # Update the current line

            # Print the transcription for debugging purposes
            print(" ".join(transcription))

        except Exception as e:
            logging.error(f"Error in transcription: {e}")

if __name__ == "__main__":
    asyncio.run(main())
