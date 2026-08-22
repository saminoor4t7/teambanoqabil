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


def build_cart_from_prescription(cart, prescription):
    """FR-09: prescription -> suggested cart. Only pulls items that a
    pharmacist has already confirmed (or, in low-risk MVP mode, high
    confidence + matched items) — never auto-adds unmatched/ambiguous
    lines."""
    cart.items.all().delete()
    cart.prescription = prescription
    cart.save(update_fields=["prescription"])
    for item in prescription.items.filter(medicine__isnull=False):
        if item.pharmacist_confirmed or (item.confidence or 0) >= 0.85:
            cart_item, _ = cart.items.get_or_create(medicine=item.medicine)
            cart_item.quantity = item.quantity or 1
            cart_item.save()
    return cart


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
    )

    for cart_item in cart.items.select_related("medicine"):
        inventory = InventoryItem.objects.filter(pharmacy=pharmacy, medicine=cart_item.medicine).first()
        if inventory and inventory.quantity_in_stock < cart_item.quantity:
            raise ValueError(f"Insufficient stock for {cart_item.medicine}.")

        OrderItem.objects.create(
            order=order,
            medicine=cart_item.medicine,
            quantity=cart_item.quantity,
            unit_price=inventory.selling_price if inventory else 0,
        )

    order.recalc_total()
    cart.items.all().delete()
    cart.prescription = None
    cart.save(update_fields=["prescription"])
    return order
