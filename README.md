# Project Overview

![](https://github.com/phbui/real-time-captioning-extension/blob/main/captioning.gif)

## Builds

Self-explanatory.

## Extension

A Chrome extension that captures audio and sends it to a WebSocket server.

### TODO:

- Get the transcription response from the WebSocket server and display it on the screen.

### How to Run:

1. Go to `chrome://extensions` in Chrome.
2. Press **Load Unpacked**.
3. Load the entire `extension` folder.
4. A microphone icon should appear in your extension toolbar.
5. Ensure the WebSocket server is running.

## Secret Keys

Self-explanatory.

## Server

A WebSocket server that takes audio input and transcribes it.

### TODO:

- Add LLM-based contextual enrichment to the transcriptions.

### How to Run:

1. Open the `server` folder in your terminal.
2. Set up the virtual environment:

   ```bash
   python -m venv venv
   source venv/bin/activate   # For macOS/Linux
   venv\Scripts\activate # For Windows
   ```

3. Install dependancies:

   ```bash
   pip install -r requirements.txt
   ```

   1. Run Websocket server:

   ```bash
   python websocket.py

   ```

   2. Run Tests:
      Run test\_[...].bat
