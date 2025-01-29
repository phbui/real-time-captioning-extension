import asyncio
import websockets
import torch
import logging

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
    
    async def handle_connection(self, websocket):
        try:
            async for message in websocket:
                if isinstance(message, bytes):
                    if self.audio_processor.is_speech(message, self.audio_processor.WHISPER_SAMPLE_RATE):
                        self.phrase_time = datetime.utcnow() - self.start_time
                        await self.audio_queue.put({"time": self.phrase_time, "audio": message})
                else:
                    print("Received text:", message)
        except websockets.ConnectionClosed:
            print("Client disconnected.")
        except Exception as e:
            print(f"Error in connection: {e}")
    
    async def transcribe_loop(self):
        logging.info("Starting transcription loop...")
        batch_buffer = bytearray()
        transcription = ['']
        phrase_timestamp = timedelta(0)
        phrase_complete = False
        
        while True:
            while not self.audio_queue.empty():
                data = await self.audio_queue.get()
                audio_data = data["audio"]
                if phrase_complete:
                    phrase_timestamp = data["time"]
                batch_buffer.extend(audio_data)
            
            phrase_complete = False
            if batch_buffer:
                audio_tensor = self.audio_processor.preprocess_audio(batch_buffer)
                audio_tensor = torch.from_numpy(audio_tensor).to("cuda", non_blocking=True)
                result = self.model.transcribe(audio_tensor)
                segments = result.get("segments", [])
                formatted_segments, _ = self.audio_processor.process_time_segments(phrase_timestamp, segments)
                now = datetime.utcnow() - self.start_time
                if self.phrase_time and now - self.phrase_time > timedelta(seconds=self.audio_processor.PHRASE_TIMEOUT):
                    phrase_complete = True
                if phrase_complete:
                    transcription.append("".join(formatted_segments))
                    batch_buffer.clear()
                else:
                    transcription[-1] = "".join(formatted_segments)
                print("[Transcription]")
                print(" ".join(transcription), end="\n")
            await asyncio.sleep(0.1)
    
    async def main(self):
        asyncio.create_task(self.transcribe_loop())
        async with websockets.serve(self.handle_connection, self.host, self.port):
            print(f"Starting WebSocket server at ws://{self.host}:{self.port}")
            await asyncio.Future()

if __name__ == "__main__":
    server = TranscriptionServer()
    asyncio.run(server.main())
