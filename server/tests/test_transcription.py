import pyaudio
import numpy as np
import whisper
import torch
import threading
from torchaudio.functional import resample
from datetime import datetime 

# Whisper model initialization (uses GPU if available)
# You can choose 'tiny', 'base', 'small', 'medium', 'large', etc.
model = whisper.load_model("turbo", device="cuda")

# Audio configuration
INPUT_SAMPLE_RATE = 48000  # Microphone sample rate (most mics use 48kHz)
WHISPER_SAMPLE_RATE = 16000  # Whisper expects 16kHz
CHANNELS = 1  # Mono audio
CHUNK_SIZE = 1024  # Size of audio chunks to capture
FORMAT = pyaudio.paInt16  # 16-bit PCM

# Initialize PyAudio
audio = pyaudio.PyAudio()

# Open the microphone stream
stream = audio.open(
    format=FORMAT,
    channels=CHANNELS,
    rate=INPUT_SAMPLE_RATE,
    input=True,
    frames_per_buffer=CHUNK_SIZE,
)

# Global buffer to accumulate audio data
audio_buffer = bytearray()
buffer_lock = threading.Lock()

# Transcription interval (seconds)
TRANSCRIBE_INTERVAL = 1.0


def capture_audio():
    """
    Continuously captures audio from the microphone and appends it to the global buffer.
    """
    print("Capturing audio from the microphone...")
    while True:
        data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        with buffer_lock:
            audio_buffer.extend(data)


def transcribe_audio():
    """
    Periodically processes audio from the buffer and transcribes it using Whisper.
    """
    while True:
        threading.Event().wait(TRANSCRIBE_INTERVAL)

        # Lock the buffer and copy data for processing
        with buffer_lock:
            if len(audio_buffer) == 0:
                continue
            raw_data = bytes(audio_buffer)
            audio_buffer.clear()

        # Convert raw PCM data to float32 numpy array
        samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32)

        # Resample from 48kHz to 16kHz
        audio_tensor = torch.from_numpy(samples)
        audio_tensor_16k = resample(audio_tensor, orig_freq=INPUT_SAMPLE_RATE, new_freq=WHISPER_SAMPLE_RATE)

        # Whisper expects a 1D array of float32 samples at 16kHz
        audio_for_whisper = audio_tensor_16k.numpy() / 32768.0  # Normalize PCM to [-1.0, 1.0]

        # Run Whisper transcription
        result = model.transcribe(audio_for_whisper, fp16=False)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}]: {result['text']}")


if __name__ == "__main__":
    try:
        # Start the audio capture and transcription threads
        threading.Thread(target=capture_audio, daemon=True).start()
        threading.Thread(target=transcribe_audio, daemon=True).start()

        threading.Event().wait()
    finally:
        # Clean up resources
        stream.stop_stream()
        stream.close()
        audio.terminate()
