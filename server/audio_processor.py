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
    PHRASE_TIMEOUT = 2  # Silence duration to determine a new phrase

    def __init__(self):
        self.vad = webrtcvad.Vad()
        self.vad.set_mode(3)  # Moderate aggressiveness

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
        self.clusterer = hdbscan.HDBSCAN(min_cluster_size=4, metric="euclidean", prediction_data=True)
    
    def is_speech(self, audio_chunk, sample_rate):
        frame_duration_ms = (len(audio_chunk) / (sample_rate / 1000))
        if frame_duration_ms not in [10, 20, 30]:
            return False
        return self.vad.is_speech(audio_chunk, sample_rate)

    def extract_speaker_embedding(self, audio):
        """Extracts speaker embedding using ECAPA-TDNN."""
        audio_tensor = torch.tensor(audio).unsqueeze(0).to(self.device)
        embedding = self.speaker_model.encode_batch(audio_tensor).squeeze(0).detach()

        if embedding.dim() == 1:  
            embedding = embedding.unsqueeze(0)
        elif embedding.dim() == 3:  
            embedding = embedding.squeeze(0)

        embedding = torch.nn.functional.normalize(embedding, p=2, dim=-1)

        return embedding

    def identify_speaker(self, embedding):
        """Identify or assign a new speaker ID using PyTorch KNN (GPU)."""
        if embedding.dim() == 3:  # If shape is [1, 1, 192], convert to [1, 192]
            embedding = embedding.squeeze(0)

        if self.speaker_embeddings.shape[0] > 0:
            # Compute pairwise distances
            distances = torch.cdist(embedding.unsqueeze(0), self.speaker_embeddings)
            nearest_dist, nearest_idx = torch.min(distances, dim=1)
            print(f"nearest_dist, nearest_idx = {nearest_dist}, {nearest_idx}")
            nearest_dist = nearest_dist.squeeze().min().item()
            nearest_idx = nearest_idx.flatten()[0].item()

            if nearest_dist < 1: # Distance threshold for reidentification
                return self.speaker_ids[nearest_idx]

        # If no match is found, register a new speaker
        new_speaker_id = f"SPEAKER_{self.next_speaker_id}"
        self.speaker_ids.append(new_speaker_id)

        if self.speaker_embeddings.shape[0] == 0:
            self.speaker_embeddings = embedding  # Direct assignment if empty
        else:
            self.speaker_embeddings = torch.cat((self.speaker_embeddings, embedding), dim=0)

        self.next_speaker_id += 1
        return new_speaker_id

    def diarize_speaker(self, raw_data, start_time):
        """
        Processes the entire audio buffer at once (no chunking).
        Extracts a single speaker embedding and assigns speaker labels.
        Returns speaker ID and timestamp.
        """
        print("\n🔹 Starting Diarization Process...")

        # Convert raw audio to float32
        samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
        num_samples = len(samples)
        duration = num_samples / self.WHISPER_SAMPLE_RATE
        print(f"🟢 Audio Samples Extracted: {num_samples} samples (~{duration:.2f} sec)")

        # 🔥 Extract Speaker Embedding for the Entire Audio Input
        embedding = self.extract_speaker_embedding(samples)
        print(f"🔍 Extracted Embedding: {embedding.shape}")

        # 🔥 Identify Speaker
        speaker_id = self.identify_speaker(embedding)
        print(f"👤 Identified Speaker: {speaker_id}")

        # 🔥 Store for Clustering
        self.speaker_embeddings = torch.cat((self.speaker_embeddings, embedding), dim=0)
        print(f"🗂 Updated Speaker Embeddings: {self.speaker_embeddings.shape}")

        # 🔥 Perform Clustering with HDBSCAN (if enough data exists)
        if len(self.speaker_embeddings) >= 4:  # Only cluster if enough samples exist
            speaker_labels = self.clusterer.fit_predict(self.speaker_embeddings.cpu().numpy())
        else:
            speaker_labels = [-1]  # Default label if clustering is not yet possible
        print(f"📊 Clustering Result: {speaker_labels}")

        # 🔥 Compute Start and End Time for the Whole Audio
        formatted_start = self.format_time(start_time)
        formatted_end = self.format_time(start_time + timedelta(seconds=duration))
        print(f"🕒 Time Interval: {formatted_start} - {formatted_end}")

        # 🔥 Return Processed Diarization Results
        speaker_results = [{
            "speaker_id": speaker_id,
            "start_time": formatted_start,
            "end_time": formatted_end,
            "speaker_labels": speaker_labels
        }]

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
