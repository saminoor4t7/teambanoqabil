"""
Response Generator — the orchestrator that ties all AI services together.

Flow:
  1. Preprocess user input (language detection, normalisation).
  2. Classify intent (NLP engine).
  3. Extract entities (NLP engine).
  4. Route to the appropriate handler:
     - medicine_search  → Medicine Matcher → Ollama
     - category_browse  → Category filter
     - medicine_info    → Medicine Matcher (single) → Ollama
     - image_match      → Image Analyzer → Ollama
     - order_status     → Order lookup
     - general          → Ollama (chit-chat)
  5. Generate conversational response via Ollama (with fallback).
  6. Save chat message to DB.
"""

import logging

from django.db import transaction

from apps.catalog.models import Medicine
from apps.catalog.serializers import MedicineSerializer
from apps.ai_agent.models import ChatMessage, ChatSession
from apps.customer.models import Cart
from apps.medical_store.models import InventoryItem, PharmacyProfile

from . import image_analyzer, medicine_matcher, nlp_engine, ollama_client
from .language_processor import preprocess

logger = logging.getLogger(__name__)


def _medicine_cards(customer, medicines: list[dict]) -> tuple[list[dict], str]:
    """Add pharmacy-specific price and stock data to matched medicines."""
    cart, _ = Cart.objects.get_or_create(customer=customer)
    pharmacy = cart.pharmacy if cart.pharmacy_id else PharmacyProfile.objects.filter(
        is_verified=True, is_open=True
    ).first()
    medicine_ids = [item["medicine"].id for item in medicines]
    inventory = {}
    if pharmacy and medicine_ids:
        inventory = {
            item.medicine_id: item
            for item in InventoryItem.objects.filter(
                pharmacy=pharmacy, medicine_id__in=medicine_ids
            )
        }

    cards = []
    for item in medicines:
        medicine = item["medicine"]
        stock = inventory.get(medicine.id)
        card = {
            **MedicineSerializer(medicine).data,
            "match_score": item["score"],
            "price": float(stock.selling_price) if stock else 0,
            "stock": stock.quantity_in_stock if stock else 0,
            "available": bool(stock and stock.quantity_in_stock > 0),
            "pharmacy": pharmacy.business_name if pharmacy else "No pharmacy selected",
            "pharmacy_id": pharmacy.id if pharmacy else None,
        }
        cards.append(card)
    return cards, pharmacy.business_name if pharmacy else "No pharmacy selected"


def handle_message(
    session: ChatSession,
    user_text: str,
    image_data: bytes | None = None,
) -> dict:
    """Process one user message and return the full agent response.

    Returns:
        {
            "intent": str,
            "confidence": float,
            "language": str,
            "entities": dict,
            "medicines": list[dict],   # serialised Medicine objects
            "response": str,           # conversational response text
        }
    """
    # 1. Preprocess
    normalised, english, language = preprocess(user_text)

    # 2. Intent + entities
    intent, confidence = nlp_engine.get_classifier().predict(english)
    entities = nlp_engine.extract_entities(english)

    # Override intent if an image was uploaded
    if image_data is not None:
        intent = "image_match"
        confidence = 1.0

    # 3. Route to handler
    medicines = []
    context_text = ""

    if intent == "medicine_search":
        medicines, context_text = _handle_medicine_search(english, entities, language)

    elif intent == "category_browse":
        medicines, context_text = _handle_category_browse(english, entities, language)

    elif intent == "medicine_info":
        medicines, context_text = _handle_medicine_info(english, entities, language)

    elif intent == "image_match":
        medicines, context_text = _handle_image_match(image_data, language)

    elif intent == "order_status":
        context_text = _handle_order_status(session, language)

    else:
        context_text = ""  # general chat — no context needed

    # 4. Build chat history for Ollama
    history = list(
        session.messages.order_by("-created_at").values("role", "content")[:6]
    )
    history.reverse()

    # 5. Generate response
    response_text = ollama_client.generate_response(
        user_message=user_text,
        context=context_text,
        chat_history=[{"role": m["role"], "content": m["content"]} for m in history],
        language=language,
    )

    # 6. Save to DB
    user_msg = ChatMessage.objects.create(
        session=session,
        role="user",
        content=user_text,
        intent=intent,
        detected_language=language,
        entities=entities,
    )
    agent_msg = ChatMessage.objects.create(
        session=session,
        role="agent",
        content=response_text,
        intent=intent,
    )
    # Link matched medicines
    for m in medicines:
        user_msg.matched_medicines.add(m["medicine"])

    # Update session language
    if language != session.language:
        session.language = language
        session.save(update_fields=["language", "updated_at"])

    medicine_cards, pharmacy_name = _medicine_cards(session.customer, medicines)
    return {
        "intent": intent,
        "confidence": round(confidence, 2),
        "language": language,
        "entities": entities,
        "medicines": medicine_cards,
        "pharmacy": pharmacy_name,
        "response": response_text,
    }


# ── Intent handlers ───────────────────────────────────────────────────

def _handle_medicine_search(query: str, entities: dict, language: str) -> tuple[list[dict], str]:
    results = medicine_matcher.search(query, top_k=5, min_score=0.3)

    # If entity has specific dosage, filter results
    if entities.get("dosages"):
        target_dosage = entities["dosages"][0].lower()
        filtered = [r for r in results if target_dosage in (r["medicine"].strength or "").lower()]
        if filtered:
            results = filtered

    # If entity has form, boost matching forms
    if entities.get("form"):
        target_form = entities["form"]
        for r in results:
            if r["medicine"].form and target_form in r["medicine"].form.lower():
                r["score"] = min(r["score"] + 0.1, 1.0)
        results.sort(key=lambda x: x["score"], reverse=True)

    context = ollama_client.summarise_medicine_results(results, language)
    return results, context


def _handle_category_browse(query: str, entities: dict, language: str) -> tuple[list[dict], str]:
    # Extract category name from the query
    from apps.catalog.models import Category

    categories = Category.objects.all()
    best_cat = None
    for cat in categories:
        if cat.name.lower() in query.lower():
            best_cat = cat
            break

    if best_cat:
        results = medicine_matcher.search_by_category(best_cat.name)
    else:
        # Fallback: semantic search with the full query
        results = medicine_matcher.search(query, top_k=10, min_score=0.25)

    context = ollama_client.summarise_medicine_results(results, language)
    return results, context


def _handle_medicine_info(query: str, entities: dict, language: str) -> tuple[list[dict], str]:
    # Try to find the specific medicine mentioned
    results = medicine_matcher.search(query, top_k=3, min_score=0.4)
    if results:
        # Build a detailed info context for Ollama
        med = results[0]["medicine"]
        info_lines = [
            f"Medicine: {med.name} {med.strength}",
            f"Generic name: {med.generic_name or 'N/A'}",
            f"Form: {med.form or 'N/A'}",
            f"Category: {med.category.name if med.category_id else 'N/A'}",
            f"Brand: {med.brand.name if med.brand_id else 'N/A'}",
            f"Requires prescription: {'Yes' if med.requires_prescription else 'No'}",
        ]
        if med.description:
            info_lines.append(f"Description: {med.description}")
        context = "\n".join(info_lines)
    else:
        context = "Medicine not found in catalog."

    return results[:1] if results else [], context


def _handle_image_match(image_data: bytes | None, language: str) -> tuple[list[dict], str]:
    if not image_data:
        msg = "Koi image upload nahi hui." if language == "roman_ur" else "No image was uploaded."
        return [], msg

    results = image_analyzer.match_image(image_data, top_k=5, min_score=0.4)
    context = ollama_client.summarise_medicine_results(results, language)
    return results, context


def _handle_order_status(session: ChatSession, language: str) -> str:
    """Look up the customer's most recent order status."""
    from apps.orders.models import Order

    orders = Order.objects.filter(
        customer=session.customer
    ).order_by("-created_at")[:1]

    if not orders:
        if language == "roman_ur":
            return "Aap ka koi order nahi mila."
        return "No orders found for your account."

    order = orders[0]
    if language == "roman_ur":
        return f"Aap ka order #{order.id} ka status: {order.status}"
    return f"Order #{order.id} — Status: {order.status}"
