import os
import time
import asyncio
import websockets
import torch
import json
from datetime import datetime, timedelta
from whisper_model import WhisperModel
from audio_processor import AudioProcessor
from collections import defaultdict

class TranscriptionServer:
    def __init__(self, host="localhost", port=8765):
        self.host = host
        self.port = port
        self.model = WhisperModel()
        self.audio_processor = AudioProcessor()
        self.audio_queue = asyncio.Queue()
        self.transcription_queue = asyncio.Queue()
        self.start_time = datetime.utcnow()
        self.phrase_time = None
        self.phrase_complete = False
        self.socket_task = None
        self.batch_buffer = bytearray()
        self.diarization_queue = asyncio.Queue() 
        self.transcription_obj = [{}]
        self.diarization_obj = {}
        self.structured_transcription = None
    
    async def handle_connection(self, websocket):
        try:
            async for message in websocket:
                    if isinstance(message, bytes):
                        if self.audio_processor.is_speech(message, self.audio_processor.WHISPER_SAMPLE_RATE):
                            self.phrase_time = datetime.utcnow() - self.start_time
                            await self.audio_queue.put({"time": self.phrase_time, "audio": message})
                    else:
                        data = json.loads(message)
                        action = data.get("action")
                        match (action):
                            case "startTranscription":
                                print(message)
                                print("Starting transcription.")
                                # Ensure only one transcription task runs at a time
                                if self.socket_task and not self.socket_task.done():
                                    print("Transcription is already running.")
                                    return
                                
                                # Start the transcription loop as a background task
                                self.socket_task = asyncio.create_task(self.transcribe_loop())

                            case "endTranscription":
                                print(message)
                                print("Ending transcription.")

                                self.end_transcription()

                                # Cancel the running socket_task if it exists
                                if self.socket_task:
                                    self.socket_task.cancel()
                                    try:
                                        await self.socket_task  # Ensure proper cancellation
                                    except asyncio.CancelledError:
                                        print("Transcription task successfully stopped.")
                                    self.socket_task = None  # Clear reference to the task

        except websockets.ConnectionClosed:
            print("Client disconnected.")

    def update_transcription(self):
        self.structured_transcription = self.parse_transcript(self.diarization_obj, self.transcription_obj)

    def end_transcription(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        save_dir = os.path.join(current_dir, "transcriptions")
        os.makedirs(save_dir, exist_ok=True)
        file_name = "transcription_" + time.time() + ".json"
        file_path = os.path.join(save_dir, file_name)
        with open(file_path, "w") as f:
            json.dump(self.structured_transcription, f, indent=4)

        print(f"Saved to {file_path}") 

    def get_overlap(self, start1, end1, start2, end2):
        """Calculate overlap duration between two time intervals."""
        overlap = max(0, min(end1, end2) - max(start1, start2))
        total_duration = min(end1 - start1, end2 - start2)  # Normalize by the shorter segment
        return overlap / total_duration if total_duration > 0 else 0  # Return overlap ratio

    def parse_transcript(self, diarization, transcription):
        """Aligns transcriptions with speaker diarization based on timestamps."""
        
        def parse_timestamp(ts):
            """Convert timestamp (HH:MM:SS.sss) into seconds."""
            h, m, s = map(float, ts.split(":"))
            return h * 3600 + m * 60 + s

        structured_transcript = []

        # Process each speaker's segments
        for speaker, data in diarization.items():
            for segment in data["time_segments"]:
                segment_start = parse_timestamp(segment["start_time"])
                segment_end = parse_timestamp(segment["end_time"])
                speaker_texts = []
                overlap_durations = defaultdict(float) 

                # Find transcription that matches this time segment
                for transcript_group in transcription:
                    for entry in transcript_group:
                        text_start = parse_timestamp(entry["start"])
                        text_end = parse_timestamp(entry["end"])

                        # Compute overlap
                        overlap = self.get_overlap(text_start, text_end, segment_start, segment_end)

                        if overlap > 0:  # There is some overlap
                            overlap_durations[speaker] += overlap  # Track total overlap per speaker
                            speaker_texts.append(entry["text"])

                if speaker_texts:
                    structured_transcript.append({
                        "speaker": speaker,
                        "start_time": segment["start_time"],
                        "end_time": segment["end_time"],
                        "text": " ".join(speaker_texts)
                    })

        # Add any remaining transcription that wasn’t assigned a speaker
        for transcript_group in transcription:
            for entry in transcript_group:
                text_start = parse_timestamp(entry["start"])
                text_end = parse_timestamp(entry["end"])

                # Check if already assigned in previous processing
                already_assigned = any(
                    text_start >= parse_timestamp(t["start_time"]) and text_end <= parse_timestamp(t["end_time"])
                    for t in structured_transcript
                )

                if not already_assigned:
                    structured_transcript.append({
                        "speaker": "UNKNOWN",  # Assign to UNKNOWN
                        "start_time": entry["start"],
                        "end_time": entry["end"],
                        "text": entry["text"]
                    })

        # Sort transcript chronologically by start time
        structured_transcript.sort(key=lambda x: parse_timestamp(x["start_time"]))

        return structured_transcript

    def print_transcript(self):
        final_transcript = self.parse_transcript(self.diarization_obj, self.transcription_obj)
        print("\n[TRANSCRIPT]")
        for entry in final_transcript:
            print(f"[{entry['start_time']}-{entry['end_time']}] {entry['speaker']}: {entry['text']}")

    def enqueue_diarization_data(self, audio_data, start_time):
        """Puts audio data into the diarization queue asynchronously."""
        try:
            self.diarization_queue.put_nowait({"audio": audio_data, "start_time": start_time})
        except asyncio.QueueFull:
            print("Warning: Diarization queue is full, dropping data!")  

    def process_transcription(self):
        self.print_transcript()
        self.update_transcription()

    async def run_diarization(self, audio_data, start_time):
        """
        Runs diarization asynchronously and updates speaker tracking.
        """
        self.diarization_obj = self.audio_processor.diarize_speaker(audio_data, start_time)
        self.process_transcription()

    async def run_transcription(self, audio_data, start_time):
        """
        Runs transcription asynchronously, returning formatted text.
        """
        audio_tensor = self.audio_processor.preprocess_audio(audio_data)
        audio_tensor = torch.from_numpy(audio_tensor).to("cuda", non_blocking=True)

        result = self.model.transcribe(audio_tensor)
        segments = result.get("segments", [])
        transcription_obj = self.audio_processor.process_time_segments(start_time, segments)

        now = datetime.utcnow() - self.start_time
        self.phrase_complete = self.phrase_time and now - self.phrase_time > timedelta(seconds=self.audio_processor.PHRASE_TIMEOUT)

        self.transcription_obj[-1] = transcription_obj
        if self.phrase_complete:
            self.transcription_obj.append({})
            diarization_data = bytes(self.batch_buffer)
            self.enqueue_diarization_data(diarization_data, start_time)  
            self.batch_buffer.clear()  # Clear all processed transcription data

        self.process_transcription()

    async def transcribe_loop(self):
        print("Starting transcription loop...")

        phrase_timestamp = timedelta(0)
        diarization_tasks = set() 
        
        while True:
            while not self.audio_queue.empty():
                data = await self.audio_queue.get()
                audio_data = data["audio"]
                if self.phrase_complete:
                    phrase_timestamp = data["time"]
                self.batch_buffer.extend(audio_data)
            
            self.phrase_complete = False

            if self.batch_buffer:
                transcription_task = asyncio.create_task(self.run_transcription(self.batch_buffer, phrase_timestamp))
                await transcription_task  # Process transcription without blocking

            if not self.diarization_queue.empty():
                diarization_data = await self.diarization_queue.get()
                diarization_task = asyncio.create_task(self.run_diarization(diarization_data["audio"], diarization_data["start_time"]))
                diarization_tasks.add(diarization_task)
                diarization_task.add_done_callback(diarization_tasks.discard)
  
            await asyncio.sleep(0.1)
    
    async def main(self):
        async with websockets.serve(self.handle_connection, self.host, self.port):
            print(f"Starting WebSocket server at ws://{self.host}:{self.port}")
            await asyncio.Future()

if __name__ == "__main__":
    server = TranscriptionServer()
    try:
        asyncio.run(server.main())  # Run the event loop
    except KeyboardInterrupt:
        print("KeyboardInterrupt received, shutting down...")