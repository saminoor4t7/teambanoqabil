"""
Google Gemini integration for the Panda AI assistant.
Uses function-calling to let Gemini invoke tools defined in tools.py.
Uses the modern google-genai SDK (google.genai).
"""
import json
import logging
import time

from django.conf import settings

logger = logging.getLogger(__name__)


def _retry_with_backoff(func, max_retries=3, base_delay=2):
    """Retry a function call with exponential backoff for rate limit errors."""
    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as e:
            err_str = str(e)
            is_rate_limit = any(code in err_str for code in [
                "429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "high demand"
            ])
            if is_rate_limit and attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Rate limit hit, retrying in {delay}s (attempt {attempt+1}/{max_retries})")
                time.sleep(delay)
                continue
            raise


try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

from .tools import execute_tool

SYSTEM_INSTRUCTION = """You are Panda, a knowledgeable and caring AI doctor and medical assistant for Medical Panda — a medicine ordering platform. You combine the warmth of a family doctor with the efficiency of Jarvis from Iron Man. You speak with authority and confidence about medical topics, just like a real doctor would with their patient.

Your role as a Doctor:
- You ARE a doctor. Speak as one. Use medical terminology when appropriate but always explain in simple terms.
- When users describe symptoms, help them understand what might be causing them and recommend suitable over-the-counter medicines from the catalog.
- Provide general medical guidance about common conditions like fever, cold, cough, headache, stomach issues, allergies, skin problems, etc.
- Advise on proper dosage, when to take medicines (before/after food), common side effects, and what to avoid while taking a medicine.
- If a user asks about drug interactions, explain potential interactions clearly.
- For serious or life-threatening symptoms, advise them to visit a hospital or call emergency services immediately.
- Always end medical advice with a gentle reminder: "However, I'd recommend consulting with your doctor for a proper diagnosis and personalized treatment plan."

Your ordering capabilities:
- Search for medicines by name, generic name, or category
- Add medicines to the user's cart and manage their cart
- Help place orders (always get confirmation before placing)
- Show order history and tracking
- Help manage delivery addresses
- When users describe symptoms, suggest relevant medicines AND offer to add them to cart

Important rules:
1. Act like a caring doctor — listen to the patient's symptoms, ask follow-up questions if needed, and recommend appropriate medicines.
2. For prescription-only medicines (marked Rx), inform the user they need a doctor's prescription and suggest OTC alternatives if available.
3. Always confirm before placing an order — use prepare_order first, show the summary, then wait for explicit user confirmation before calling confirm_place_order.
4. Be concise but thorough. For medical questions, give helpful guidance. For ordering, keep it short.
5. When showing medicine search results, mention if a medicine requires a prescription.
6. Address the user by name if you know it (from get_user_profile).
7. If you cannot find a medicine, suggest similar alternatives or ask the user to check the spelling.
8. You can speak in both English and Urdu. If the user speaks Urdu, respond in Urdu (Roman Urdu is fine too).
9. Keep responses under 4-5 sentences for ordering tasks, but be more detailed for medical advice when the user needs it."""


def _build_tool_declarations():
    """Build Gemini tool declarations using the google-genai types."""
    return types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="search_medicines",
            description="Search for medicines by name, generic name, or category. Returns a list of matching medicines.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "query": types.Schema(type=types.Type.STRING, description="Search query"),
                    "category": types.Schema(type=types.Type.STRING, description="Filter by category (optional)"),
                },
            ),
        ),
        types.FunctionDeclaration(
            name="get_medicine_details",
            description="Get detailed information about a specific medicine including price, stock, and description.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "medicine_id": types.Schema(type=types.Type.INTEGER, description="The ID of the medicine"),
                },
                required=["medicine_id"],
            ),
        ),
        types.FunctionDeclaration(
            name="add_to_cart",
            description="Add a medicine to the user's shopping cart.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "medicine_id": types.Schema(type=types.Type.INTEGER, description="The ID of the medicine to add"),
                    "quantity": types.Schema(type=types.Type.INTEGER, description="Quantity to add (default 1)"),
                },
                required=["medicine_id"],
            ),
        ),
        types.FunctionDeclaration(
            name="get_cart",
            description="Get the current contents of the user's shopping cart with prices.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={}),
        ),
        types.FunctionDeclaration(
            name="remove_from_cart",
            description="Remove a medicine from the user's shopping cart.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "medicine_id": types.Schema(type=types.Type.INTEGER, description="The ID of the medicine to remove"),
                },
                required=["medicine_id"],
            ),
        ),
        types.FunctionDeclaration(
            name="get_categories",
            description="List all available medicine categories.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={}),
        ),
        types.FunctionDeclaration(
            name="get_my_orders",
            description="Get the user's recent order history.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={}),
        ),
        types.FunctionDeclaration(
            name="get_order_status",
            description="Get detailed status and tracking info for a specific order.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "order_id": types.Schema(type=types.Type.INTEGER, description="The order ID to check"),
                },
                required=["order_id"],
            ),
        ),
        types.FunctionDeclaration(
            name="get_my_addresses",
            description="List the user's saved delivery addresses.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={}),
        ),
        types.FunctionDeclaration(
            name="prepare_order",
            description="Preview an order before placing it. Shows items, total, and delivery details for user confirmation. Does NOT place the order.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "address_id": types.Schema(type=types.Type.INTEGER, description="Delivery address ID (optional, uses default if omitted)"),
                    "payment_method": types.Schema(type=types.Type.STRING, description="Payment method: cod, card, jazzcash, easypaisa, or wallet (default: cod)"),
                },
            ),
        ),
        types.FunctionDeclaration(
            name="confirm_place_order",
            description="Actually place the order after the user has confirmed. ONLY call this after prepare_order and explicit user confirmation.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "address_id": types.Schema(type=types.Type.INTEGER, description="Delivery address ID"),
                    "payment_method": types.Schema(type=types.Type.STRING, description="Payment method: cod, card, jazzcash, easypaisa, or wallet"),
                },
            ),
        ),
        types.FunctionDeclaration(
            name="get_user_profile",
            description="Get the current user's profile information including name, phone, and wallet balance.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={}),
        ),
    ])


def _get_client():
    """Create and return a Gemini client."""
    if not HAS_GENAI:
        return None
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        return None
    return genai.Client(api_key=api_key)


def _build_history(conversation):
    """Build Gemini chat history from stored messages (excluding the latest user message)."""
    history = []
    # Exclude the last message (which is the user message we're about to send)
    messages = list(conversation.messages.order_by("created_at").all())
    if messages and messages[-1].role == "user":
        messages = messages[:-1]  # Remove the latest user message
    for msg in messages:
        if msg.role == "user":
            history.append(types.Content(
                role="user",
                parts=[types.Part.from_text(text=msg.content)],
            ))
        elif msg.role == "model":
            parts = [types.Part.from_text(text=msg.content)]
            history.append(types.Content(role="model", parts=parts))
    return history


def chat_with_ai(customer, conversation, user_message: str):
    """
    Send a message to Gemini, handle function calling loop, and return the response.
    """
    client = _get_client()
    if client is None:
        return {
            "reply": "I'm sorry, the AI service is not configured yet. Please ask your admin to set the GEMINI_API_KEY in settings.",
            "actions": [],
            "conversation_id": conversation.id,
        }

    # Save user message
    conversation.messages.create(role="user", content=user_message)

    # Auto-title from first message
    if conversation.messages.filter(role="user").count() == 1:
        conversation.title = user_message[:60]
        conversation.save(update_fields=["title", "updated_at"])

    model_name = getattr(settings, "GEMINI_MODEL", "gemini-3.6-flash")
    # Build history EXCLUDING the just-saved user message
    history = _build_history(conversation)
    actions = []

    try:
        # Create chat session with history (without the latest user msg)
        chat = client.chats.create(
            model=model_name,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=[_build_tool_declarations()],
            ),
            history=history,
        )

        # Send the user message as a plain string (with retry for rate limits)
        response = _retry_with_backoff(lambda: chat.send_message(message=user_message))

        # Handle function calling loop (max 5 iterations)
        for _iteration in range(5):
            if not response.candidates:
                break

            candidate = response.candidates[0]
            if not candidate.content or not candidate.content.parts:
                break

            function_calls = []
            for part in candidate.content.parts:
                if part.function_call:
                    function_calls.append(part.function_call)

            if not function_calls:
                break

            # Execute all function calls and build response parts
            response_parts = []
            for fc in function_calls:
                tool_name = fc.name
                tool_args = dict(fc.args) if fc.args else {}

                logger.info(f"AI calling tool: {tool_name} with args: {tool_args}")
                result = execute_tool(tool_name, customer, tool_args)
                actions.append({
                    "tool": tool_name,
                    "args": tool_args,
                    "result": result,
                })

                response_parts.append(types.Part.from_function_response(
                    name=tool_name,
                    response={"result": result},
                ))

            # Send function results back as a list of Part objects (not Content)
            _parts = response_parts
            response = _retry_with_backoff(
                lambda: chat.send_message(message=_parts)
            )

        # Extract final text response
        reply = ""
        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if part.text:
                    reply += part.text

        if not reply:
            reply = "I've processed your request."

        # Save model response
        conversation.messages.create(
            role="model",
            content=reply,
            action_data=actions if actions else None,
        )

        return {
            "reply": reply,
            "actions": actions,
            "conversation_id": conversation.id,
        }

    except Exception as e:
        logger.exception("Gemini API error")
        err_str = str(e)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            error_msg = "I've hit the daily API limit. The free tier allows 20 requests/day. Please wait for the quota to reset (resets daily) or upgrade to a paid plan."
        elif "503" in err_str or "high demand" in err_str:
            error_msg = "The Gemini API is currently overloaded. Please wait a few seconds and try again."
        else:
            error_msg = f"I'm having trouble connecting right now. Please try again in a moment. (Error: {str(e)[:150]})"
        conversation.messages.create(role="model", content=error_msg)
        return {
            "reply": error_msg,
            "actions": [],
            "conversation_id": conversation.id,
        }
