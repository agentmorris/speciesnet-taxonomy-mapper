import os
import google.generativeai as genai

def list_models():
    api_key = os.environ.get("GOOGLE_API_KEY")
    
    # Try reading from gemini-key.txt
    if not api_key and os.path.exists("gemini-key.txt"):
        try:
            with open("gemini-key.txt", "r") as f:
                api_key = f.read().strip()
        except Exception as e:
            print(f"Error reading gemini-key.txt: {e}")

    if not api_key:
        print("No API key found. Please set GOOGLE_API_KEY or create gemini-key.txt")
        return

    genai.configure(api_key=api_key)

    print("Fetching available models...")
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(f"- {m.name}")
    except Exception as e:
        print(f"Error listing models: {e}")

if __name__ == "__main__":
    list_models()
