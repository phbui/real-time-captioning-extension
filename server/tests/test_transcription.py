import sys
import pyaudio
import numpy as np
import whisper
import torch
import threading
from torchaudio.functional import resample
import webrtcvad
import logging
import wave
from PyQt6.QtWidgets import QApplication, QTextEdit, QVBoxLayout, QWidget, QPushButton, QFileDialog
from PyQt6.QtCore import QThread, pyqtSignal

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Whisper model initialization (uses GPU if available)
logging.info("Loading Whisper model...")
model = whisper.load_model("turbo", device="cuda" if torch.cuda.is_available() else "cpu")
logging.info("Whisper model loaded successfully.")

# Audio configuration
INPUT_SAMPLE_RATE = 48000  # Microphone sample rate
WHISPER_SAMPLE_RATE = 16000  # Whisper expects 16kHz
CHANNELS = 1  # Mono audio
FORMAT = pyaudio.paInt16  # 16-bit PCM
FRAME_DURATION_MS = 20  # Frame duration in ms (10, 20, or 30 ms)
CHUNK_SIZE = int(INPUT_SAMPLE_RATE * FRAME_DURATION_MS / 1000)  # Samples per chunk

# Initialize PyAudio
logging.info("Initializing PyAudio...")
audio = pyaudio.PyAudio()
stream = audio.open(
    format=FORMAT,
    channels=CHANNELS,
    rate=INPUT_SAMPLE_RATE,
    input=True,
    frames_per_buffer=CHUNK_SIZE,
)
logging.info("PyAudio initialized successfully.")

# Voice Activity Detector
vad = webrtcvad.Vad()
vad.set_mode(2)  # Moderate aggressiveness

# Global buffers
audio_buffer = bytearray()  # For transcription
raw_audio_buffer = bytearray()  # For saving recordings
buffer_lock = threading.Lock()

# Transcription interval (seconds)
TRANSCRIBE_INTERVAL = 3.0


def is_speech(audio_chunk, sample_rate):
    """Check if the audio chunk contains speech using WebRTC VAD."""
    if len(audio_chunk) < 0:  # 16-bit PCM = 2 bytes per sample
        raise ValueError("Audio chunk size does not match expected frame duration")
    return vad.is_speech(audio_chunk, sample_rate)


class AudioCaptureThread(QThread):
    """Thread for capturing audio and appending it to buffers."""
    def run(self):
        logging.info("Starting audio capture thread...")
        while True:
            try:
                raw_data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                if is_speech(raw_data, INPUT_SAMPLE_RATE):
                    with buffer_lock:
                        audio_buffer.extend(raw_data)  # For transcription
                        raw_audio_buffer.extend(raw_data)  # For saving
            except Exception as e:
                logging.error(f"Error in audio capture: {e}")
                break


class TranscriptionThread(QThread):
    """Thread for transcribing audio and updating the GUI."""
    transcription_updated = pyqtSignal(str)

    def run(self):
        logging.info("Starting transcription thread...")
        transcription = ""
        while self.isRunning():
            self.msleep(int(TRANSCRIBE_INTERVAL * 1000))  # Wait for interval
            with buffer_lock:
                if len(audio_buffer) < 0:  
                    logging.debug("Not enough audio data for transcription. Skipping...")
                    continue
                raw_data = bytes(audio_buffer)
                audio_buffer.clear()

            # Convert raw PCM to float32 numpy array
            samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32)
            audio_tensor = torch.from_numpy(samples)
            audio_tensor_16k = resample(audio_tensor, orig_freq=INPUT_SAMPLE_RATE, new_freq=WHISPER_SAMPLE_RATE)

            audio_for_whisper = audio_tensor_16k.numpy() / 32768.0  # Normalize to [-1.0, 1.0]

            # Run Whisper transcription with context refinement
            result = model.transcribe(
                audio_for_whisper,
                fp16=True,
                condition_on_previous_text=True,
                no_speech_threshold=2.0,
                verbose=True,
                language="en",
                suppress_tokens=""  # Adjusted to reduce hallucinations
            )

            # Update both refined and accumulated transcriptions
            new_chunk = result["text"]
            transcription += new_chunk  # Append the new chunk for context

            # Emit the refined transcription for display
            self.transcription_updated.emit(transcription)


class TranscriptionApp(QWidget):
    """Main application for real-time transcription."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Real-Time Whisper Transcription")
        self.setGeometry(100, 100, 800, 400)

        # UI Components
        self.layout = QVBoxLayout()
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.layout.addWidget(self.text_edit)

        # Download Button
        self.download_button = QPushButton("Download Recording")
        self.download_button.clicked.connect(self.download_recording)
        self.layout.addWidget(self.download_button)

        self.setLayout(self.layout)

        # Threads
        self.audio_thread = AudioCaptureThread()
        self.transcription_thread = TranscriptionThread()
        self.transcription_thread.transcription_updated.connect(self.update_text)

        # Start threads
        logging.info("Starting audio and transcription threads...")
        self.audio_thread.start()
        self.transcription_thread.start()

    def update_text(self, transcription):
        """Update the transcription text."""
        logging.debug("Updating transcription text in the UI.")
        self.text_edit.setPlainText(transcription)

    def download_recording(self):
        """Save the audio buffer to a WAV file."""
        logging.info("Downloading the recording...")
        with buffer_lock:
            if len(raw_audio_buffer) == 0:
                logging.warning("Raw audio buffer is empty. Nothing to download.")
                return

            # Open save dialog
            file_path, _ = QFileDialog.getSaveFileName(self, "Save Recording", "", "WAV Files (*.wav)")
            if file_path:
                try:
                    with wave.open(file_path, "wb") as wav_file:
                        wav_file.setnchannels(1)  # Mono
                        wav_file.setsampwidth(2)  # 16-bit audio
                        wav_file.setframerate(INPUT_SAMPLE_RATE)  # 48 kHz
                        wav_file.writeframes(bytes(raw_audio_buffer))  # Write raw audio buffer
                    logging.info(f"Recording saved to: {file_path}")
                except Exception as e:
                    logging.error(f"Failed to save recording: {e}")

    def closeEvent(self, event):
        """Ensure proper cleanup on application exit."""
        logging.info("Closing application and cleaning up resources.")
        self.audio_thread.terminate()
        self.transcription_thread.terminate()
        stream.stop_stream()
        stream.close()
        audio.terminate()
        event.accept()


def main():
    """Main entry point."""
    logging.info("Launching application...")
    app = QApplication(sys.argv)
    window = TranscriptionApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
