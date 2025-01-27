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