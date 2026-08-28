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
