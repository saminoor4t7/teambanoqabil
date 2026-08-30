"""
Ollama client — conversational AI layer.

Calls a locally running Ollama instance to:
  1. Generate natural-language responses in English or Roman Urdu.
  2. Enhance medicine search results with helpful context.
  3. Handle follow-up questions in a chat session.

Ollama must be running at OLLAMA_BASE_URL (default http://localhost:11434).
Uses the /api/generate endpoint — no API key needed.

If Ollama is unavailable, the agent degrades gracefully and returns
structured results without the conversational wrapper.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = getattr(settings, "OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT = getattr(settings, "OLLAMA_TIMEOUT", 30)

# ── System prompt for the pharmacy assistant persona ──────────────────
SYSTEM_PROMPT = """You are Medical Panda AI, a helpful pharmacy assistant.
You help customers find medicines, understand dosage information, and answer
health-related questions. You speak in a friendly, professional tone.

Rules:
- Only recommend medicines that are in the catalog — never invent medicines.
- Always advise consulting a doctor for serious conditions.
- Keep responses concise (2-3 sentences for search results, 1 sentence for greetings).
- If the user speaks Roman Urdu, respond in Roman Urdu. If English, respond in English.
- For medicine results, mention: name, strength, what it's used for, and whether it needs a prescription.

You have access to the following medicine search results to answer the user's question:
{context}"""


def is_available() -> bool:
    """Check if Ollama is running and reachable."""
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def generate_response(
    user_message: str,
    context: str = "",
    chat_history: list[dict] | None = None,
    language: str = "en",
) -> str:
    """Generate a conversational response using Ollama.

    Args:
        user_message: The user's latest message.
        context: Medicine search results or other context for the prompt.
        chat_history: Previous messages in the conversation.
        language: 'en' or 'roman_ur' — affects the system prompt hint.

    Returns:
        The generated response text, or a fallback structured response
        if Ollama is unavailable.
    """
    system = SYSTEM_PROMPT.format(context=context or "No specific medicine context available.")
    if language == "roman_ur":
        system += "\n\nRespond in Roman Urdu (Urdu written in English script)."

    # Build the prompt with chat history
    prompt_parts = []
    if chat_history:
        for msg in chat_history[-6:]:  # last 6 messages for context
            role = "User" if msg["role"] == "user" else "Assistant"
            prompt_parts.append(f"{role}: {msg['content']}")
    prompt_parts.append(f"User: {user_message}")
    prompt_parts.append("Assistant:")
    prompt = "\n".join(prompt_parts)

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "system": system,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "num_predict": 256,
                },
            },
            timeout=OLLAMA_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["response"].strip()
    except requests.RequestException as exc:
        logger.warning("Ollama unavailable (%s) — returning fallback response", exc)
        return _fallback_response(user_message, context, language)


def _fallback_response(user_message: str, context: str, language: str) -> str:
    """Simple template-based fallback when Ollama is not running."""
    if not context or context == "No specific medicine context available.":
        if language == "roman_ur":
            return "Main Medical Panda AI hoon. Aap ko konsi dawai chahiye ya koi sawal hai?"
        return "I'm Medical Panda AI. What medicine are you looking for, or how can I help?"

    if language == "roman_ur":
        return f"Yeh rahe results:\n\n{context}"
    return f"Here are the results:\n\n{context}"


def summarise_medicine_results(results: list[dict], language: str = "en") -> str:
    """Format medicine search results into a readable context block.

    This text is fed to Ollama as context, and also used directly as
    the fallback response.
    """
    if not results:
        if language == "roman_ur":
            return "Koi medicine nahi mili. Kya aap doosre naam se try karna chahein ge?"
        return "No medicines found. Would you like to try a different name?"

    lines = []
    for i, r in enumerate(results[:5], 1):
        med = r["medicine"]
        score = r.get("score", 0)
        rx = "Prescription required" if med.requires_prescription else "Over-the-counter"
        lines.append(
            f"{i}. {med.name} {med.strength} — "
            f"{med.generic_name or 'N/A'} | "
            f"{med.category.name if med.category_id else 'N/A'} | "
            f"{rx} | "
            f"Match: {score:.0%}"
        )
    return "\n".join(lines)
