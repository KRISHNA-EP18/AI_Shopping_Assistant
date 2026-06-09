"""
Input validation for the Shopping Agent.

Checks whether a user message is shopping-related before passing
it to the agent. Off-topic messages are rejected with a polite redirect.
"""

from langchain_groq import ChatGroq
from dotenv import load_dotenv

load_dotenv()

_llm = ChatGroq(model="qwen/qwen3-32b", temperature=0)

BLOCKED_RESPONSE = (
    "I'm your shopping assistant and can only help with product searches, "
    "order history, and store-related questions. "
    "Try something like: 'Show me organic honey under $15' or 'What have I ordered before?'"
)

_SYSTEM_PROMPT = """You are a shopping assistant topic classifier for a health food grocery store.
Decide whether the user's message is related to shopping, products, orders, or personal preferences.

You are a binary classifier.

Output exactly one token:

ALLOWED
or
BLOCKED

Do not explain.
Do not add punctuation.
Do not add newlines.
Do not add reasoning.

ALLOWED examples:
- "Show me organic honey under $15"
- "What have I ordered before?"
- "I always prefer organic products"
- "Find me a good coffee"
- "Never show me items over $20"

BLOCKED examples:
- "Write me a poem about the ocean"
- "What is the capital of France?"
- "Explain quantum physics"
- "What's the weather today?"
- "Tell me a joke"
"""


def is_allowed(user_message: str) -> bool:
    if "I uploaded a product image" in user_message:
        return True
    response = _llm.invoke([
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ])

    answer = response.content.upper()

    if "ALLOWED" in answer:
        return True

    return False