import pyaudio
import webrtcvad
import numpy as np
import librosa
from datetime import timedelta

class AudioProcessor:
    WHISPER_SAMPLE_RATE = 16000  # Whisper expects 16kHz
    CHANNELS = 1  # Mono audio
    FORMAT = pyaudio.paInt16  # 16-bit PCM
    PHRASE_TIMEOUT = 0.3  # Silence duration to determine a new phrase
    
    def __init__(self):
        self.vad = webrtcvad.Vad()
        self.vad.set_mode(2)  # Moderate aggressiveness
    
    def is_speech(self, audio_chunk, sample_rate):
        frame_duration_ms = (len(audio_chunk) / (sample_rate / 1000))
        if frame_duration_ms not in [10, 20, 30]:
            return False
        return self.vad.is_speech(audio_chunk, sample_rate)

    def preprocess_audio(self, raw_data):
        samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
        target_length = self.WHISPER_SAMPLE_RATE * 30
        return librosa.util.fix_length(samples, size=target_length)
    
    @staticmethod
    def format_time(delta_seconds):
        if isinstance(delta_seconds, timedelta):
            delta_seconds = delta_seconds.total_seconds()
        hours = int(delta_seconds // 3600)
        minutes = int((delta_seconds % 3600) // 60)
        seconds = delta_seconds % 60
        return f"{hours:02}:{minutes:02}:{seconds:06.3f}"
    
    def process_time_segments(self, phrase_timestamp, segments):
        transcript_lines, transcript_obj = [], []
        for segment in segments:
            start_time = phrase_timestamp + timedelta(seconds=segment['start'])
            end_time = phrase_timestamp + timedelta(seconds=segment['end'])
            formatted_start = self.format_time(start_time)
            formatted_end = self.format_time(end_time)
            transcript_lines.append(f"[{formatted_start} - {formatted_end}] {segment['text']}")
            transcript_obj.append({"text": segment['text'], "start": formatted_start, "end": formatted_end})
        return transcript_lines, transcript_obj
