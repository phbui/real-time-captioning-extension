import numpy as np
import pyaudio
import time

# Audio configuration for the test tone
SAMPLE_RATE = 48000  # Samples per second
DURATION = 1         # Duration of the test tone in seconds
FREQUENCY = 440.0    # A4 note (440 Hz)
FORMAT = pyaudio.paInt16  # PyAudio format for 16-bit PCM
AMPLITUDE = 0.5  # Amplitude of the sine wave (0.0 to 1.0)

# Generate a test tone (sine wave)
t = np.linspace(0, DURATION, int(SAMPLE_RATE * DURATION), False)  # Time array
test_tone = (AMPLITUDE * np.sin(2 * np.pi * FREQUENCY * t) * 32767).astype(np.int16)

# Initialize PyAudio
p = pyaudio.PyAudio()

# Function to play the test tone on a specific device
def play_test_tone(device_index):
    try:
        print(f"Testing device {device_index}: {p.get_device_info_by_index(device_index)['name']}")
        # Open a stream for the specified device
        stream = p.open(
            format=FORMAT,
            channels=1,
            rate=SAMPLE_RATE,
            output=True,
            output_device_index=device_index
        )
        # Play the test tone
        stream.write(test_tone.tobytes())
        stream.stop_stream()
        stream.close()
    except Exception as e:
        print(f"Error testing device {device_index}: {e}")

# Play the test tone on all output devices
def test_all_output_devices():
    for i in range(p.get_device_count()):
        device_info = p.get_device_info_by_index(i)
        if device_info["maxOutputChannels"] > 0:  # Only test output devices
            play_test_tone(i)
            time.sleep(1)  # Short pause between tests

if __name__ == "__main__":
    print("Testing all available audio output devices...")
    test_all_output_devices()
    p.terminate()
