"""Creates the Groq LLM client used by the classification tool."""
from langchain_groq import ChatGroq

from app.config import GROQ_API_KEY, GROQ_MODEL


def get_llm() -> ChatGroq:
    if not GROQ_API_KEY or GROQ_API_KEY == "your_groq_api_key_here":
        raise RuntimeError("GROQ_API_KEY is missing. Put your Groq key in the .env file.")
    return ChatGroq(
        model=GROQ_MODEL,
        api_key=GROQ_API_KEY,
        temperature=0,
        max_tokens=1500,  # reasoning tokens count too, so leave room
        max_retries=2,
        timeout=30,
    )
