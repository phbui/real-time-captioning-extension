class PCMWorkletProcessor extends AudioWorkletProcessor {
  process(inputs, outputs) {
    // `inputs[0]` is the first input, containing channel data
    const inputChannelData = inputs[0];
    // `outputs[0]` is the first output, for playback
    const outputChannelData = outputs[0];

    if (inputChannelData.length > 0) {
      const leftChannel = inputChannelData[0];
      const rightChannel =
        inputChannelData.length > 1 ? inputChannelData[1] : inputChannelData[0]; // Use left channel if mono

      // Pass through stereo for playback
      outputChannelData[0].set(leftChannel);
      if (outputChannelData.length > 1) {
        outputChannelData[1].set(rightChannel);
      }

      // Downmix to mono for sending to the server
      const monoSamples = new Float32Array(leftChannel.length);
      for (let i = 0; i < leftChannel.length; i++) {
        monoSamples[i] = (leftChannel[i] + rightChannel[i]) / 2; // Average left and right channels
      }

      // Send the mono audio to the main thread
      this.port.postMessage(monoSamples);
    } else {
      // No input data? Fill outputs with silence
      for (let channel = 0; channel < outputChannelData.length; channel++) {
        outputChannelData[channel].fill(0);
      }
    }

    // return true => keep processor alive
    return true;
  }
}

// Must match the name used in AudioWorkletNode constructor
registerProcessor("pcm-worklet-processor", PCMWorkletProcessor);
