import pyaudio
import webrtcvad
import numpy as np
import librosa
import torch
import torch.nn.functional as F
from datetime import timedelta
from speechbrain.inference import SpeakerRecognition
import openai
import os
from dotenv import load_dotenv

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY") #get api key from laptop OS
if not openai.api_key:
    raise ValueError("OpenAI API key not found. Please set the OPENAI_API_KEY environment variable.")

class AudioProcessor:
    WHISPER_SAMPLE_RATE = 16000  # Whisper expects 16kHz
    CHANNELS = 1  # Mono audio
    FORMAT = pyaudio.paInt16  # 16-bit PCM
    PHRASE_TIMEOUT = 2  # Silence duration to determine a new phrase

    def __init__(self):
        self.vad = webrtcvad.Vad()
        self.vad.set_mode(3)  

        # Load ECAPA-TDNN for speaker embeddings (GPU optimized)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.speaker_model = SpeakerRecognition.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            run_opts={"device": self.device}
        )

        self.speaker_dim = 192  
        self.speaker_embeddings = {}  # 🔹 Store multiple embeddings per speaker
        self.speaker_history = {}
        self.next_speaker_id = 0
        self.similarity_threshold = 0.5

        openai.api_key = os.getenv("OPENAI_API_KEY") #get api key from laptop OS

    def is_speech(self, audio_chunk, sample_rate):
        """Check if the audio contains speech using WebRTC VAD."""
        frame_duration_ms = (len(audio_chunk) / (sample_rate / 1000))
        if frame_duration_ms not in [10, 20, 30]:
            return False
        return self.vad.is_speech(audio_chunk, sample_rate)

    def extract_speaker_embedding(self, audio):
        """Extracts and normalizes speaker embedding."""
        min_duration_samples = self.WHISPER_SAMPLE_RATE * 3
        audio = librosa.util.fix_length(audio, size=min_duration_samples)
        audio_tensor = torch.tensor(audio).unsqueeze(0).to(self.device)
        embedding = self.speaker_model.encode_batch(audio_tensor).squeeze(0).detach()

        if embedding.dim() == 1:  
            embedding = embedding.unsqueeze(0)
        elif embedding.dim() == 3:  
            embedding = embedding.squeeze(0)

        embedding = torch.nn.functional.normalize(embedding, p=2, dim=-1)
        return embedding.view(1, -1)  

    def find_closest_speaker(self, embedding):
        """Find the closest speaker using cosine similarity with adaptive thresholding."""
        if not self.speaker_embeddings:
            return None, 0.0  

        best_match = None
        best_similarity = 0.0

        for speaker_id, stored_embeddings in self.speaker_embeddings.items():
            similarities = F.cosine_similarity(embedding, stored_embeddings)
            max_sim = torch.max(similarities).item()  

            if max_sim > best_similarity:
                best_similarity = max_sim
                best_match = speaker_id

        # 🔹 Use progressive relaxation for close matches
        adjusted_threshold = self.similarity_threshold - 0.1  
        if best_similarity >= adjusted_threshold:
            return best_match, best_similarity  

        return None, best_similarity  

    def update_speaker_embedding(self, speaker_id, new_embedding):
        """Averages new embeddings with previous ones for stability."""
        if speaker_id not in self.speaker_embeddings:
            self.speaker_embeddings[speaker_id] = new_embedding
        else:
            # 🔹 Running average to smooth variations
            self.speaker_embeddings[speaker_id] = (
                self.speaker_embeddings[speaker_id] * 0.7 + new_embedding * 0.3
            )

    def diarize_speaker(self, raw_data, start_time):
        """Processes audio and assigns speaker IDs using cosine similarity."""
        samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
        embedding = self.extract_speaker_embedding(samples)
        if embedding is None:
            return self.speaker_history
        
        embedding = embedding.view(1, -1)  
        matched_speaker, similarity = self.find_closest_speaker(embedding)

        if matched_speaker is None:
            speaker_id = f"SPEAKER_{self.next_speaker_id}"
            self.speaker_embeddings[speaker_id] = embedding  
            self.next_speaker_id += 1
        else:
            speaker_id = matched_speaker
            self.update_speaker_embedding(speaker_id, embedding)  

        formatted_start = self.format_time(start_time)
        formatted_end = self.format_time(start_time + timedelta(seconds=len(samples) / self.WHISPER_SAMPLE_RATE))

        if speaker_id not in self.speaker_history:
            self.speaker_history[speaker_id] = {"time_segments": []}

        self.speaker_history[speaker_id]["time_segments"].append({
            "start_time": formatted_start,
            "end_time": formatted_end,
            "similarity": similarity
        })

        return self.speaker_history
    
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
        transcript_obj = []
        for segment in segments:
            start_time = phrase_timestamp + timedelta(seconds=segment['start'])
            end_time = phrase_timestamp + timedelta(seconds=segment['end'])
            formatted_start = self.format_time(start_time)
            formatted_end = self.format_time(end_time)
            transcript_obj.append({"text": segment['text'], "start": formatted_start, "end": formatted_end})
        return transcript_obj
    
    def add_context_w_llm(self, caption, history):
        """
        Adds the context to caption from the LLM based on the prompt given in llm_prompt.txt.
        """

        try: 
            with open("llm_prompt.txt", "r") as file:
                prompt_template = file.read()
            prompt = prompt_template.format(caption=caption, history=history) # format with caption inserted at end of prompt

            response = openai.ChatCompletion.create(
                model="gpt-4o-mini", #change for different openai model
                messages=[{"role": "system", "content": "You are an AI that improves captions for neurodivergent users."},
                      {"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.7,
            )

            contextualized_transcript = response['choices'][0]['message']['content'].strip()

            return contextualized_transcript
        
        except FileNotFoundError:
            raise FileNotFoundError("The prompt file 'llm_prompt.txt' was not found.")
        except openai.error.OpenAIError as e:
            raise RuntimeError(f"OpenAI API error: {e}")
        
        
    
