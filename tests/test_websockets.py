import asyncio
import websockets

async def test():
    uri = "ws://3.141.7.60:5000/transcribe"
    async with websockets.connect(uri) as websocket:
        print("Connected to WebSocket server!")
        await websocket.close()

asyncio.run(test())
