"""Phase 2 test: check tool calling and structured output on the Groq model."""
import os
import sys

from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

load_dotenv()

model_name = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
llm = ChatGroq(model=model_name, temperature=0, max_tokens=1000, max_retries=1)


@tool
def get_technician_count(category: str) -> int:
    """Return how many technicians are available for a category such as plumbing or electrical."""
    return 2


class Classification(BaseModel):
    category: str = Field(description="One of: plumbing, electrical, cleaning, other")
    urgency: str = Field(description="One of: low, medium, high")


failed = False

print("--- Test 1: tool calling ---")
try:
    llm_with_tools = llm.bind_tools([get_technician_count])
    reply = llm_with_tools.invoke(
        "How many plumbing technicians are available? Use the tool."
    )
    print("Tool calls requested:", reply.tool_calls)
    if not reply.tool_calls:
        print("WARNING: the model did not request a tool call.")
        failed = True
except Exception as error:
    print("Tool calling failed:", type(error).__name__, error)
    failed = True

print("--- Test 2: structured output ---")
try:
    structured_llm = llm.with_structured_output(Classification)
    result = structured_llm.invoke("Water is leaking under my kitchen sink.")
    print("Structured result:", result)
except Exception as error:
    print("Structured output failed:", type(error).__name__, error)
    failed = True

sys.exit(1 if failed else 0)
