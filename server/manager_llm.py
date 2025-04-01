from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

class Manager_LLM:
    def __init__(self, model_name="TheBloke/Mistral-7B-Instruct-v0.1-GPTQ"):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            device_map=self.device,
            use_safetensors=True,
            revision="main",
            torch_dtype=torch.float16,
        )
        self.chat_template = "[INST] {prompt} [/INST]"

    def generate(self, prompt: str, max_tokens: int = 512,
                 temperature: float = 0.7, top_p: float = 0.95) -> str:
        # Format prompt using the chat template
        formatted_prompt = self.tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}],
            tokenize=False,
            add_generation_prompt=True
        )
        # Tokenize the prompt and move to the device where the model is loaded
        inputs = self.tokenizer(formatted_prompt, return_tensors="pt").to(self.model.device)

        # Generate response in inference mode (no gradient tracking)
        with torch.inference_mode():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                do_sample=True,
                pad_token_id=self.tokenizer.eos_token_id
            )
        # Decode the new tokens (excluding the input prompt)
        return self.tokenizer.decode(
            outputs[0][inputs.input_ids.shape[1]:],
            skip_special_tokens=True
        )

if __name__ == "__main__":
    print("Checking CUDA availability...")
    print(f"PyTorch CUDA available: {torch.cuda.is_available()}")
    print(f"CUDA devices: {torch.cuda.device_count()}")

    llm = Manager_LLM()
    print("Mistral 7B Chat Interface (type 'quit' to exit)")
    while True:
        user_input = input("\nYou: ")
        if user_input.lower() in ["quit", "exit"]:
            break
        response = llm.generate(user_input)
        print(f"\nAssistant: {response}")
