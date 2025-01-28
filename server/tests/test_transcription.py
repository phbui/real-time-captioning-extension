import sys
import pyaudio
import numpy as np
import whisper
import torch
import threading
import webrtcvad
import logging
import wave
from datetime import datetime, timedelta
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
CHUNK_SIZE = int(INPUT_SAMPLE_RATE * 0.02)  # 20ms frames
PHRASE_TIMEOUT = 1.0  # Seconds of silence to consider as a new phrase

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
phrase_time = None


def is_speech(audio_chunk, sample_rate):
    """Check if the audio chunk contains speech using WebRTC VAD."""
    if len(audio_chunk) < 0:  # 16-bit PCM = 2 bytes per sample
        raise ValueError("Audio chunk size does not match expected frame duration")
    return vad.is_speech(audio_chunk, sample_rate)


class AudioCaptureThread(QThread):
    """Thread for capturing audio and appending it to buffers."""
    def run(self):
        global phrase_time
        logging.info("Starting audio capture thread...")
        while True:
            try:
                raw_data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                if isinstance(raw_data, bytes):  # Check if the message contains PCM audio data
                    if is_speech(raw_data, INPUT_SAMPLE_RATE):
                        with buffer_lock:
                            audio_buffer.extend(raw_data)  # For transcription
                            raw_audio_buffer.extend(raw_data)  # For saving
                        phrase_time = datetime.utcnow()  # Update the last time speech was detected
            except Exception as e:
                logging.error(f"Error in audio capture: {e}")
                break


class TranscriptionThread(QThread):
    """Thread for transcribing audio and updating the GUI."""
    transcription_updated = pyqtSignal(str)

    def run(self):
        global phrase_time
        logging.info("Starting transcription thread...")
        transcription = [""]
        while self.isRunning():
            self.msleep(100)  # Check every 100ms

            now = datetime.utcnow()
            phrase_complete = False

            # Check if enough time has passed since the last detected speech
            if phrase_time and now - phrase_time > timedelta(seconds=PHRASE_TIMEOUT):
                phrase_complete = True

            with buffer_lock:
                if len(audio_buffer) == 0 or not phrase_complete:
                    continue
                raw_data = bytes(audio_buffer)
                audio_buffer.clear()

            # Convert raw PCM to float32 numpy array
            samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32)
            audio_tensor = torch.from_numpy(samples)
            audio_tensor_16k = torch.nn.functional.interpolate(
                audio_tensor.unsqueeze(0).unsqueeze(0),
                scale_factor=WHISPER_SAMPLE_RATE / INPUT_SAMPLE_RATE,
                mode='linear',
                align_corners=False
            ).squeeze().numpy() / 32768.0

            try:
                # Run Whisper transcription
                result = model.transcribe(
                    audio_tensor_16k,
                    fp16=True,
                    logprob_threshold=-1.0,
                    no_speech_threshold=2.0,
                    hallucination_silence_threshold=1.0,
                    compression_ratio_threshold=1.0,
                    verbose=True,
                    language="en",
                    condition_on_previous_text=True,
                    suppress_tokens=""  # Adjusted to reduce hallucinations
                )
                text = result["text"].strip()

                # If the phrase is complete, start a new transcription line
                if phrase_complete:
                    transcription.append(text)
                else:
                    transcription[-1] = text

                # Emit updated transcription
                self.transcription_updated.emit(" ".join(transcription))
            except Exception as e:
                logging.error(f"Error in transcription: {e}")


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
