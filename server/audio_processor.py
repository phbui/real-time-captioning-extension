import pyaudio
import webrtcvad
import numpy as np
import librosa
import torch
from datetime import timedelta
from speechbrain.inference import SpeakerRecognition
import hdbscan

class AudioProcessor:
    WHISPER_SAMPLE_RATE = 16000  # Whisper expects 16kHz
    CHANNELS = 1  # Mono audio
    FORMAT = pyaudio.paInt16  # 16-bit PCM
    PHRASE_TIMEOUT = 0.3  # Silence duration to determine a new phrase
    
    def __init__(self):
        self.vad = webrtcvad.Vad()
        self.vad.set_mode(2)  # Moderate aggressiveness

        # Load ECAPA-TDNN for speaker embeddings (GPU optimized)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.speaker_model = SpeakerRecognition.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            run_opts={"device": self.device}
        )

        # Initialize PyTorch KNN (GPU-accelerated)
        self.speaker_dim = 192  # ECAPA-TDNN embedding size
        self.speaker_embeddings = torch.empty((0, self.speaker_dim), dtype=torch.float32, device=self.device)
        self.speaker_ids = []
        self.next_speaker_id = 0

        # HDBSCAN for online speaker clustering
        self.clusterer = hdbscan.HDBSCAN(min_cluster_size=2, metric="euclidean", prediction_data=True)
    
    def is_speech(self, audio_chunk, sample_rate):
        frame_duration_ms = (len(audio_chunk) / (sample_rate / 1000))
        if frame_duration_ms not in [10, 20, 30]:
            return False
        return self.vad.is_speech(audio_chunk, sample_rate)

    def extract_speaker_embedding(self, audio):
        """Extracts speaker embedding using ECAPA-TDNN."""
        audio_tensor = torch.tensor(audio).unsqueeze(0).to(self.device)
        embedding = self.speaker_model.encode_batch(audio_tensor).squeeze(0).detach()
        return embedding

    def identify_speaker(self, embedding):
        """Identify or assign a new speaker ID using PyTorch KNN (GPU)."""
        if self.speaker_embeddings.shape[0] > 0:
            # Compute pairwise distances
            distances = torch.cdist(embedding.unsqueeze(0), self.speaker_embeddings)
            nearest_idx = torch.argmin(distances).item()
            
            if distances[0, nearest_idx] < 0.5:  # Distance threshold for reidentification
                return self.speaker_ids[nearest_idx]

        # If no match is found, register a new speaker
        new_speaker_id = f"SPEAKER_{self.next_speaker_id}"
        self.speaker_ids.append(new_speaker_id)
        self.speaker_embeddings = torch.cat((self.speaker_embeddings, embedding.unsqueeze(0)), dim=0)
        self.next_speaker_id += 1
        return new_speaker_id

    def diarize_speaker(self, raw_data, start_time):
        """
        Takes in 1 second of audio, extracts speaker embeddings, and assigns speaker labels for multiple speakers.
        Returns a list of speaker labels and timestamps.
        """
        print("\n🔹 Starting Diarization Process...")
        
        # Convert raw audio to float32
        samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
        print(f"🟢 Audio Samples Extracted: {len(samples)} samples")

        chunk_size = int(self.WHISPER_SAMPLE_RATE * 0.25)  # 250ms per chunk
        num_chunks = len(samples) // chunk_size
        print(f"🟡 Processing {num_chunks} chunks (each {chunk_size} samples)")

        speaker_results = []

        for i in range(num_chunks):
            chunk_start = i * chunk_size
            chunk_end = (i + 1) * chunk_size
            audio_chunk = samples[chunk_start:chunk_end]
            print(f"\n🔹 Processing Chunk {i + 1}/{num_chunks} (Samples {chunk_start} - {chunk_end})")

            # Skip silent segments
            if not self.is_speech(audio_chunk.tobytes(), self.WHISPER_SAMPLE_RATE):
                print(f"🔕 Chunk {i + 1}: Skipped (No Speech Detected)")
                continue

            print(f"🔊 Chunk {i + 1}: Speech Detected, Extracting Embedding...")

            # Extract speaker embedding
            embedding = self.extract_speaker_embedding(audio_chunk)
            print(f"🔍 Extracted Embedding: {embedding.shape}")

            # Identify speaker
            speaker_id = self.identify_speaker(embedding)
            print(f"👤 Identified Speaker: {speaker_id}")

            # Store for clustering
            self.speaker_embeddings = torch.cat((self.speaker_embeddings, embedding.unsqueeze(0)), dim=0)
            print(f"🗂 Updated Speaker Embeddings: {self.speaker_embeddings.shape}")

            # Perform online clustering with HDBSCAN
            speaker_labels = self.clusterer.fit_predict(self.speaker_embeddings.cpu().numpy())
            print(f"📊 Clustering Result: {speaker_labels}")

            # Compute chunk start and end time
            formatted_start = self.format_time(start_time + timedelta(seconds=i * 0.25))
            formatted_end = self.format_time(start_time + timedelta(seconds=(i + 1) * 0.25))
            print(f"🕒 Time Interval: {formatted_start} - {formatted_end}")

            speaker_results.append({
                "speaker_id": speaker_id,
                "start_time": formatted_start,
                "end_time": formatted_end,
                "speaker_labels": speaker_labels
            })

        print("\n✅ Diarization Process Completed.")
        return speaker_results if speaker_results else None  # Return None if no speech detected

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
