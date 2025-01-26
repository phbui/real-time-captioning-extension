import boto3
from fastapi import FastAPI, WebSocket
from fastapi.responses import JSONResponse
import asyncio
import uuid

app = FastAPI()

# Initialize AWS Transcribe client
transcribe_client = boto3.client("transcribe", region_name="us-east-1")

@app.websocket("/transcribe")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Client connected")

    try:
        while True:
            audio_data = await websocket.receive_bytes()
            job_name = f"transcription-{uuid.uuid4()}"
            response = transcribe_client.start_transcription_job(
                TranscriptionJobName=job_name,
                Media={"MediaFileUri": "s3://your-audio-bucket/audio-file.wav"},
                MediaFormat="wav",
                LanguageCode="en-US",
            )
            # Poll for job completion
            while True:
                status = transcribe_client.get_transcription_job(
                    TranscriptionJobName=job_name
                )
                if status["TranscriptionJob"]["TranscriptionJobStatus"] in [
                    "COMPLETED",
                    "FAILED",
                ]:
                    break
                await asyncio.sleep(5)

            if status["TranscriptionJob"]["TranscriptionJobStatus"] == "COMPLETED":
                transcription = status["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
                await websocket.send_text(transcription)

    except Exception as e:
        print(f"Error: {e}")
        await websocket.close()
