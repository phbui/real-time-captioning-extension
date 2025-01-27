import asyncio
import websockets
import numpy as np
import pyaudio

# Audio configuration
SAMPLE_RATE = 48000  # Ensure this matches the sample rate from the browser
CHANNELS = 1         # Mono audio
FORMAT = pyaudio.paInt16  # PyAudio format for 16-bit PCM
DEVICE_INDEX = 2


# Initialize PyAudio
p = pyaudio.PyAudio()

# Open a PyAudio stream for playback
stream = p.open(
    format=FORMAT,
    channels=CHANNELS,
    rate=SAMPLE_RATE,
    output=True,
    output_device_index=DEVICE_INDEX 
)

async def handle_connection(websocket):
    try:
        async for message in websocket:
            if isinstance(message, bytes):
                # Convert raw 16-bit PCM data into a NumPy array
                samples = np.frombuffer(message, dtype=np.int16)
                # Play the audio using PyAudio
                stream.write(samples.tobytes())
                print(f"Played audio chunk of size: {len(samples)} samples")
            else:
                print("Received text:", message)

    except websockets.ConnectionClosed:
        print("Client disconnected.")
    except Exception as e:
        print(f"Error: {e}")

async def main():
    print("Starting WebSocket server at ws://localhost:8765")
    async with websockets.serve(handle_connection, "localhost", 8765):
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        # Clean up the PyAudio resources when the server shuts down
        stream.stop_stream()
        stream.close()
        p.terminate()
