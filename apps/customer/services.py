"""
Business logic that crosses the customer/pharmacy/order boundary lives
here rather than in views, so it stays testable and reusable (e.g. by a
future AI-chat endpoint that also needs to "place an order").
"""
import requests
from django.conf import settings
from django.db import transaction

from apps.medical_store.models import InventoryItem, PharmacyProfile


def request_ai_prescription_extraction(prescription):
    """
    Calls the separate AI microservice (Vision/OCR + LLM) described in the
    architecture doc. This function is intentionally the ONLY place that
    talks to that service — Django never lets the LLM write directly to
    PrescriptionItem; it only ever writes to Prescription.ai_raw_response,
    which a human/service layer then turns into confirmed PrescriptionItem
    rows (FR-04/FR-05).
    """
    try:
        resp = requests.post(
            f"{settings.AI_SERVICE_BASE_URL}/v1/prescription/extract",
            json={"prescription_id": prescription.id, "file_url": prescription.file.url},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        # AI service unreachable — leave prescription in "needs_review" so
        # a pharmacist can key it in manually rather than silently failing.
        return None


@transaction.atomic
def place_order_from_cart(cart, delivery_address, payment_method):
    from apps.orders.models import Order, OrderItem

    if not cart.items.exists():
        raise ValueError("Cart is empty.")
    if not cart.pharmacy_id:
        raise ValueError("No pharmacy selected for this cart.")

    pharmacy = PharmacyProfile.objects.select_for_update().get(pk=cart.pharmacy_id)

    order = Order.objects.create(
        customer=cart.customer,
        pharmacy=pharmacy,
        prescription=cart.prescription,
        delivery_address=delivery_address,
        payment_method=payment_method,
        coupon_code=cart.coupon_code,
        delivery_fee=settings.DELIVERY_FEE,
    )

    for cart_item in cart.items.select_related("medicine"):
        inventory = InventoryItem.objects.select_for_update().filter(
            pharmacy=pharmacy, medicine=cart_item.medicine
        ).first()
        if not inventory:
            raise ValueError(f"{cart_item.medicine} is not available at {pharmacy}.")
        if inventory.quantity_in_stock < cart_item.quantity:
            raise ValueError(f"Insufficient stock for {cart_item.medicine}.")
        if inventory.selling_price <= 0 or inventory.discount_percentage >= 100:
            raise ValueError(f"{cart_item.medicine} has no valid selling price at {pharmacy}.")
        if cart_item.medicine.requires_prescription and cart.prescription_id is None:
            raise ValueError(
                f"{cart_item.medicine.name} requires a prescription. "
                "Attach an uploaded prescription to the cart before ordering."
            )

        OrderItem.objects.create(
            order=order,
            medicine=cart_item.medicine,
            quantity=cart_item.quantity,
            unit_price=(
                inventory.selling_price * (1 - inventory.discount_percentage / 100)
                
            ),
        )
        inventory.quantity_in_stock -= cart_item.quantity
        inventory.save(update_fields=["quantity_in_stock", "updated_at"])

    order.recalc_total()
    cart.items.all().delete()
    cart.prescription = None
    cart.save(update_fields=["prescription"])
    return order


# ── Prescription AI pipeline (B7) ──────────────────────────────────────

def _extract_items_from_ai_response(raw):
    """Normalise the AI service's stored payload into a list of item dicts.

    Accepts several tolerated shapes so we don't break when the microservice
    contract changes:
      {"items": [...]} | {"medicines": [...]} | {"prescription_items": [...]}
      | a bare list | an "ai_extract"/"data" wrapper.
    """
    if not isinstance(raw, dict):
        return []
    payload = raw
    for key in ("data", "result", "ai_extract"):
        if isinstance(payload.get(key), (dict, list)):
            payload = payload[key]
            break
    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        raw_items = None
        for key in ("items", "medicines", "prescription_items", "drugs"):
            if isinstance(payload.get(key), list):
                raw_items = payload[key]
                break
        if raw_items is None:
            return []
    else:
        return []

    items = []
    for entry in raw_items:
        if not isinstance(entry, dict):
            # A bare string line like "Panadol 500mg"
            entry = {"raw_medicine_text": str(entry)}
        raw_text = str(entry.get("raw_medicine_text") or entry.get("name") or entry.get("text") or "").strip()
        if not raw_text:
            continue
        items.append({
            "raw_medicine_text": raw_text,
            "strength": str(entry.get("strength") or ""),
            "dosage": str(entry.get("dosage") or ""),
            "frequency": str(entry.get("frequency") or ""),
            "duration": str(entry.get("duration") or ""),
            "special_instructions": str(entry.get("special_instructions") or ""),
            "quantity": entry.get("quantity"),
            "confidence": entry.get("confidence"),
        })
    return items


def parse_ai_extraction_into_items(prescription):
    """Turn Prescription.ai_raw_response into PrescriptionItem rows (B7).

    Idempotent: only creates rows when none exist yet, so re-running after
    a pharmacist has hand-edited items won't duplicate or clobber them.
    """
    from .models import PrescriptionItem

    if prescription.items.exists():
        return prescription.items.all()

    if not prescription.ai_raw_response:
        return prescription.items.all()

    product = _extract_items_from_ai_response(prescription.ai_raw_response)
    for entry in product:
        PrescriptionItem.objects.create(
            prescription=prescription,
            raw_medicine_text=entry["raw_medicine_text"],
            strength=entry["strength"],
            dosage=entry["dosage"],
            frequency=entry["frequency"],
            duration=entry["duration"],
            special_instructions=entry["special_instructions"],
            quantity=entry["quantity"] if isinstance(entry["quantity"], int) and entry["quantity"] > 0 else None,
            confidence=entry["confidence"] if isinstance(entry["confidence"], (int, float)) else None,
        )
    return prescription.items.all()


def match_medicine_to_catalog(raw_text, pharmacy=None):
    """Resolve an OCR line to a catalog Medicine.

    Tries semantic search first (if embeddings exist), then falls back to
    a name icontains match on the active catalog for the target pharmacy.
    Returns the best Medicine or None.
    """
    from apps.catalog.models import Medicine

    query = raw_text.strip()
    if not query:
        return None

    base_qs = Medicine.objects.filter(is_active=True)
    if pharmacy is not None:
        # Only medicines actually in stock (as inventory rows) at this pharmacy.
        from apps.medical_store.models import InventoryItem
        ids = InventoryItem.objects.filter(pharmacy=pharmacy).values_list("medicine_id", flat=True)
        base_qs = base_qs.filter(id__in=list(ids))

    candidates = base_qs.filter(name__icontains=query).order_by("name")
    if candidates.exists():
        return candidates.first()

    # Fall back to the first word(s) — OCR often drops dosage suffix.
    for head in (query, query.split()[0] if query.split() else query):
        m = base_qs.filter(name__iexact=head).first()
        if m:
            return m
        m = base_qs.filter(generic_name__icontains=head).first()
        if m:
            return m

    return None


@transaction.atomic
def build_cart_from_prescription(prescription, customer):
    """Populate the customer's cart from a prescription's extracted items.

    1. Ensure PrescriptionItem rows exist (parse ai_raw_response if needed).
    2. Match each item to a catalog medicine available at the prescription's
       pharmacy and add it to the cart (respecting stock limits).
    Returns (cart, list_of_unmatched_raw_texts).
    """
    from apps.catalog.models import Medicine
    from .models import Cart

    items = parse_ai_extraction_into_items(prescription)
    try:
        cart = customer.cart
    except Cart.DoesNotExist:
        cart = Cart.objects.create(customer=customer)

    pharmacy = prescription.pharmacy or cart.pharmacy
    if pharmacy is None:
        raise ValueError("No pharmacy selected for this prescription.")

    if cart.pharmacy_id and cart.pharmacy_id != pharmacy.id:
        cart.items.all().delete()
    cart.pharmacy = pharmacy
    cart.prescription = prescription

    unmatched = []
    for item in items:
        qty = item.quantity if item.quantity and item.quantity > 0 else 1
        if item.medicine_id:
            medicine = item.medicine
        else:
            medicine = match_medicine_to_catalog(item.raw_medicine_text, pharmacy=pharmacy)
            if medicine is None:
                unmatched.append(item.raw_medicine_text)
                continue
        inventory = InventoryItem.objects.filter(
            pharmacy=pharmacy, medicine=medicine
        ).first()
        if inventory is None or inventory.selling_price <= 0:
            unmatched.append(item.raw_medicine_text)
            continue
        if inventory.quantity_in_stock > 0:
            qty = min(qty, inventory.quantity_in_stock)
        cart_item, _ = cart.items.get_or_create(medicine=medicine)
        cart_item.quantity = qty
        cart_item.save()

    cart.save(update_fields=["pharmacy", "prescription", "updated_at"])
    return cart, unmatched
