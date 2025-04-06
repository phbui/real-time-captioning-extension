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
        self.transcription_obj = [{}]
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
        self.structured_transcription = self.parse_transcript(self.transcription_obj)

    def end_transcription(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        save_dir = os.path.join(current_dir, "transcriptions")
        os.makedirs(save_dir, exist_ok=True)
        file_name = "transcription_" + str(time.time()) + ".json"
        file_path = os.path.join(save_dir, file_name)

        context_transcription = []

        for transcript in self.structured_transcription:
            transcript['context'] = self.get_context(transcript['text'], context_transcription)
            context_transcription.append(transcript)

        with open(file_path, "w") as f:
            json.dump(context_transcription, f, indent=4)

        print(f"Saved to {file_path}") 

    def get_overlap(self, start1, end1, start2, end2):
        """Calculate overlap duration between two time intervals."""
        overlap = max(0, min(end1, end2) - max(start1, start2))
        total_duration = min(end1 - start1, end2 - start2)  # Normalize by the shorter segment
        return overlap / total_duration if total_duration > 0 else 0  # Return overlap ratio

    def parse_transcript(self, transcription):
        def parse_timestamp(ts):
            """Convert timestamp (HH:MM:SS.sss) into seconds."""
            h, m, s = map(float, ts.split(":"))
            return h * 3600 + m * 60 + s

        structured_transcript = []

        for transcript_group in transcription:
            for entry in transcript_group:
                already_assigned = False
                if not already_assigned:
                    structured_transcript.append({
                    #    "speaker": "UNKNOWN",  # Assign to UNKNOWN
                        "start_time": entry["start"],
                        "end_time": entry["end"],
                        "text": entry["text"],
                        "context": entry["context"]
                    })

        # Sort transcript chronologically by start time
        structured_transcript.sort(key=lambda x: parse_timestamp(x["start_time"]))

        return structured_transcript

    def print_transcript(self):
        print("\n[TRANSCRIPT]")
        for entry in self.structured_transcription:
                print(f"[{entry['start_time']}-{entry['end_time']}]: {entry['text']}")


    def process_transcription(self):
        self.update_transcription()
        self.print_transcript() #print at the end (with the context added)

    def get_context(self, last_transcription, transcription_history):
        history = ''
        if transcription_history:
            recent_history = transcription_history[-4:]
            history = ', '.join(obj['text'] for obj in recent_history)
        return self.audio_processor.add_context_w_llm(last_transcription, f"[{history}]")

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
            self.batch_buffer.clear()  # Clear all processed transcription data

        self.process_transcription()

    async def transcribe_loop(self):
        print("Starting transcription loop...")

        phrase_timestamp = timedelta(0)
        
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