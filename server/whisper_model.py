import torch
import whisper
import torch.backends.cudnn as cudnn

cudnn.benchmark = True

class WhisperModel:
    def __init__(self, model_name="turbo"):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = whisper.load_model(model_name, device=self.device)
    
    def transcribe(self, audio_tensor):
        return self.model.transcribe(
            audio_tensor,
            fp16=True,
            logprob_threshold=-1.0,
            no_speech_threshold=2.0,
            hallucination_silence_threshold=1.0,
            compression_ratio_threshold=1.0,
            language="en",
            suppress_tokens=""
        )
