import asyncio
import websockets
import torch
import logging
import json
from datetime import datetime, timedelta
from whisper_model import WhisperModel
from audio_processor import AudioProcessor

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
        self.socket_task = None
        self.batch_buffer = bytearray()
        self.diarization_queue = asyncio.Queue() 
        self.transcription = ['']
    
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
        except Exception as e:
            print(f"Error in connection: {e}")

    async def enqueue_diarization_data(self, audio_data):
        """Puts audio data into the diarization queue asynchronously."""
        await self.diarization_queue.put(audio_data)
    
    async def run_diarization(self, audio_data, start_time):
        """
        Runs diarization asynchronously without blocking transcription.
        """
        speaker_segments = self.audio_processor.diarize_speaker(audio_data, start_time)
        if speaker_segments:
            print("[Diarization Results]")
            for segment in speaker_segments:
                print(f"{segment['start_time']} - {segment['end_time']}: {segment['speaker_id']}")

    async def run_transcription(self, audio_data, start_time):
        """
        Runs transcription asynchronously, returning formatted text.
        """
        audio_tensor = self.audio_processor.preprocess_audio(audio_data)
        audio_tensor = torch.from_numpy(audio_tensor).to("cuda", non_blocking=True)

        result = self.model.transcribe(audio_tensor)
        segments = result.get("segments", [])
        formatted_segments, _ = self.audio_processor.process_time_segments(start_time, segments)

        now = datetime.utcnow() - self.start_time
        self.phrase_complete = self.phrase_time and now - self.phrase_time > timedelta(seconds=self.audio_processor.PHRASE_TIMEOUT)


        self.transcription[-1] = "".join(formatted_segments) + " "
        if self.phrase_complete:
            self.transcription.append("...")
            diarization_data = bytes(self.batch_buffer)
            asyncio.create_task(self.enqueue_diarization_data(diarization_data))
            self.batch_buffer.clear()  # Clear all processed transcription data
        
        print("[Transcription]")
        print("".join(self.transcription))
        print("===\n")

    async def transcribe_loop(self):
        logging.info("Starting transcription loop...")

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

            # if self.diarization_queue:
            #    diarization_buffer = await self.diarization_queue.get()
            #    diarization_task = asyncio.create_task(self.run_diarization(diarization_buffer, phrase_timestamp))
            #    await diarization_task  # Wait for diarization to complete

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