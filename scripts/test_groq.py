"""Phase 2 test: make one minimal call to the Groq LLM."""
import os
import sys

from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
model_name = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

if not api_key or api_key == "your_groq_api_key_here":
    print("ERROR: GROQ_API_KEY is missing. Put your real key in the .env file.")
    sys.exit(1)

print(f"Using model: {model_name}")

llm = ChatGroq(model=model_name, temperature=0, max_tokens=1000, max_retries=1)

try:
    response = llm.invoke("Reply with exactly these words: FixFlow connection OK")
    print("Model reply:", response.content)
    print("Token usage:", response.usage_metadata)
except Exception as error:
    print("LLM call failed:", type(error).__name__)
    print(error)
    sys.exit(1)
