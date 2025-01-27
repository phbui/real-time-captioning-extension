import asyncio
import websockets
import numpy as np
import whisper
import torch
import time
import threading

from torchaudio.functional import resample

# Whisper model initialization (uses GPU if available)
# You can choose 'tiny', 'base', 'small', 'medium', 'large', etc.
model = whisper.load_model("turbo", device="cuda")  

# Audio configuration
INPUT_SAMPLE_RATE = 48000  # incoming audio sample rate
WHISPER_SAMPLE_RATE = 16000
CHANNELS = 1               # mono audio
SAMPLE_WIDTH = 2           # 16-bit PCM -> 2 bytes per sample

# A global buffer to accumulate raw audio data
audio_buffer = bytearray()
buffer_lock = threading.Lock()

# How often (in seconds) we run a transcription pass
TRANSCRIBE_INTERVAL = 5.0  

async def handle_connection(websocket):
    try:
        async for message in websocket:
            if isinstance(message, bytes):
                # Append PCM data to global buffer
                with buffer_lock:
                    audio_buffer.extend(message)
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
    Periodically reads the global audio buffer, resamples it,
    and runs it through Whisper for transcription.
    """
    while True:
        time.sleep(TRANSCRIBE_INTERVAL)

        # Pull out the current buffer contents (thread-safe)
        with buffer_lock:
            if len(audio_buffer) == 0:
                continue  # no new audio
            raw_data = bytes(audio_buffer)
            audio_buffer.clear()

        # Convert raw 16-bit PCM to float32 Tensor
        samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32)
        
        # Reshape to (num_samples, num_channels). We have 1 channel, so shape is (-1, 1)
        samples = np.reshape(samples, (-1, CHANNELS))

        # Resample from 48kHz -> 16kHz if needed
        # shape: (num_samples, 1)
        # We'll make it [1, num_samples] for torchaudio, meaning [channels, samples]
        audio_tensor = torch.from_numpy(samples.T)  # shape: [1, num_samples]
        audio_tensor_16k = resample(audio_tensor, orig_freq=INPUT_SAMPLE_RATE, new_freq=WHISPER_SAMPLE_RATE)

        # Whisper expects a 1D array of float32 samples at 16kHz
        # shape: [num_samples]
        audio_for_whisper = audio_tensor_16k.squeeze(0).cuda()  # push to GPU

        # Run transcription
        #   - If your buffer is large, this might take a bit
        #   - For real-time partial decoding, you'd do partial segments
        result = model.transcribe(audio_for_whisper, fp16=False)  
        # If using the built-in approach with file paths, you'd need to write to a temp file,
        # but we can pass raw audio as a torch tensor with the "transcribe" convenience.

        print(result["text"])

if __name__ == "__main__":
    asyncio.run(main())
