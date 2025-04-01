import os
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

load_dotenv()

secret_key = os.getenv('hf_key')

class Manager_LLM():
    def __init__(self, model_name="mistralai/Mistral-7B-Instruct-v0.3"):
        self.model_name = model_name
        self.client = InferenceClient(model=model_name, token=secret_key)

    def generate_response(self, prompt: str, max_tokens: int = 128, temperature: float = 0.2) -> str:
        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.client.chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Exception: {e}")
            return ""

if __name__ == "__main__":
    manager = Manager_LLM()

    # Main loop to prompt the model.
    print("Enter a prompt for the model. Type 'exit' to quit.")
    while True:
        prompt = input("Prompt: ")
        if prompt.strip().lower() == "exit":
            break
        
        # Generate response with some new tokens
        response = manager.generate_response(prompt)
        print("Response:", response)
