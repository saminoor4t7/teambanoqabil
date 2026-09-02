r"""
AI tool functions that Gemini can call via function-calling.
Each function receives the customer profile and the arguments dict from Gemini,
and returns a JSON-serialisable result that goes back into the conversation.
"""
import json
from django.db.models import Q

from apps.catalog.models import Medicine, Category
from apps.customer.models import Cart, CartItem, Address, CustomerProfile
from apps.medical_store.models import PharmacyProfile, InventoryItem
from apps.orders.models import Order


def _cart_for(customer: CustomerProfile) -> Cart:
    cart, _ = Cart.objects.get_or_create(customer=customer)
    return cart


def _pharmacy(customer: CustomerProfile):
    """Return the pharmacy currently attached to the customer's cart, or the first verified one."""
    cart = _cart_for(customer)
    if cart.pharmacy_id:
        return cart.pharmacy
    ph = PharmacyProfile.objects.filter(is_verified=True, is_open=True).first()
    if ph:
        cart.pharmacy = ph
        cart.save(update_fields=["pharmacy"])
    return ph


# -- search_medicines --
def _decorate_medicine_result(m, inv, pharmacy_name):
    """Shared shape for medicine cards: catalog fields + price/stock at the
    user's pharmacy so the AI can quote availability without a second call."""
    stock = int(inv.quantity_in_stock or 0) if inv else 0
    return {
        "id": m.id,
        "name": m.name,
        "generic_name": m.generic_name,
        "strength": m.strength,
        "form": m.form,
        "brand": m.brand.name if m.brand else "",
        "requires_prescription": m.requires_prescription,
        "description": m.description[:120] if m.description else "",
        "price": float(inv.selling_price) if inv else 0,
        "stock": stock,
        "available": bool(inv) and stock > 0,
        "pharmacy": pharmacy_name if inv else "",
    }


def search_medicines(customer, args):
    """Search medicines by name, generic name, or category name.
    Enriches each result with price and stock availability at the customer's pharmacy."""
    query = (args.get("query") or "").strip()
    category = (args.get("category") or "").strip()
    qs = Medicine.objects.filter(is_active=True)
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(generic_name__icontains=query))
    if category:
        qs = qs.filter(category__name__icontains=category)
    results = list(qs[:15])
    ph = _pharmacy(customer)
    pharmacy_name = ph.business_name if ph else "No pharmacy selected"
    inv_map = {}
    if ph and results:
        inv_map = {
            inv.medicine_id: inv
            for inv in InventoryItem.objects.filter(
                pharmacy=ph, medicine_id__in=[m.id for m in results]
            )
        }
    medicines = [_decorate_medicine_result(m, inv_map.get(m.id), pharmacy_name) for m in results]
    return {
        "found": len(medicines),
        "medicines": medicines,
        "pharmacy": pharmacy_name,
    }


# -- get_medicine_details --
def get_medicine_details(customer, args):
    """Get full details about a specific medicine by ID, including price and stock at the customer's pharmacy."""
    med_id = args.get("medicine_id")
    try:
        m = Medicine.objects.get(id=med_id, is_active=True)
    except Medicine.DoesNotExist:
        return {"error": f"Medicine with id {med_id} not found."}
    ph = _pharmacy(customer)
    price = 0
    stock = 0
    if ph:
        inv = InventoryItem.objects.filter(pharmacy=ph, medicine=m).first()
        if inv:
            price = float(inv.selling_price)
            stock = int(inv.quantity_in_stock or 0)
    return {
        "id": m.id,
        "name": m.name,
        "generic_name": m.generic_name,
        "strength": m.strength,
        "form": m.form,
        "brand": m.brand.name if m.brand else "",
        "category": m.category.name if m.category else "",
        "requires_prescription": m.requires_prescription,
        "description": m.description,
        "price": price,
        "stock": stock,
        "available": price > 0 and stock > 0,
        "pharmacy": ph.business_name if ph else "No pharmacy selected",
    }


# -- add_to_cart --
def add_to_cart(customer, args):
    """Add a medicine to the customer's cart. Only sells at the customer's pharmacy and respects stock."""
    try:
        quantity = max(1, int(args.get("quantity", 1)))
    except (TypeError, ValueError):
        quantity = 1
    medicine_id = args.get("medicine_id")
    try:
        medicine = Medicine.objects.get(id=medicine_id, is_active=True)
    except (Medicine.DoesNotExist, TypeError, ValueError):
        return {"error": f"Medicine #{medicine_id} not found."}

    cart = _cart_for(customer)
    ph = _pharmacy(customer)
    if not ph:
        return {"error": "No pharmacy is available right now. Please try again later."}
    if cart.pharmacy_id != ph.id:
        cart.pharmacy = ph
        cart.save(update_fields=["pharmacy"])

    inventory = InventoryItem.objects.filter(pharmacy=ph, medicine=medicine).first()
    if not inventory:
        return {
            "error": f"{medicine.name} is not stocked at {ph.business_name}. "
            "I can search for an alternative that is available.",
        }
    stock = int(inventory.quantity_in_stock or 0)
    if stock <= 0:
        return {
            "error": f"{medicine.name} is currently out of stock at {ph.business_name}. "
            "I can suggest an available alternative.",
        }

    existing = cart.items.filter(medicine=medicine).first()
    current = existing.quantity if existing else 0
    desired = current + quantity
    qty = min(desired, stock)

    if qty <= 0:
        return {"error": f"{medicine.name} is not available right now."}

    if existing is None:
        cart.items.create(medicine=medicine, quantity=qty)
    else:
        existing.quantity = qty
        existing.save(update_fields=["quantity"])

    message = f"{medicine.name} (qty {qty}) added to your cart from {ph.business_name}."
    if qty < desired:
        message += f" Only {stock} in stock, so I added {qty}."
    if medicine.requires_prescription:
        message += " ⚠️ This medicine requires a prescription — you'll need to provide it at checkout."

    return {
        "success": True,
        "message": message,
        "medicine": {
            "id": medicine.id,
            "name": medicine.name,
            "strength": medicine.strength,
            "requires_prescription": medicine.requires_prescription,
        },
        "quantity": qty,
        "unit_price": float(inventory.selling_price),
        "available_stock": stock,
        "pharmacy": ph.business_name,
    }


# -- get_cart --
def get_cart(customer, args):
    """Return the current cart contents."""
    cart = _cart_for(customer)
    items = []
    subtotal = 0
    ph = _pharmacy(customer)
    for ci in cart.items.select_related("medicine"):
        inv = InventoryItem.objects.filter(pharmacy=ph, medicine=ci.medicine).first() if ph else None
        price = float(inv.selling_price) if inv else 0
        line_total = price * ci.quantity
        subtotal += line_total
        items.append({
            "id": ci.id,
            "medicine_id": ci.medicine_id,
            "medicine_name": ci.medicine.name,
            "strength": ci.medicine.strength,
            "quantity": ci.quantity,
            "unit_price": price,
            "line_total": line_total,
        })
    return {
        "pharmacy": ph.business_name if ph else "None selected",
        "items": items,
        "item_count": len(items),
        "subtotal": subtotal,
    }


# -- remove_from_cart --
def remove_from_cart(customer, args):
    """Remove a medicine from the cart (set quantity to 0 or delete)."""
    medicine_id = args.get("medicine_id")
    cart = _cart_for(customer)
    deleted = cart.items.filter(medicine_id=medicine_id).delete()
    if deleted[0]:
        return {"success": True, "message": "Item removed from cart."}
    return {"error": "Item not found in cart."}


# -- get_categories --
def get_categories(customer, args):
    """List all medicine categories."""
    cats = Category.objects.all()
    return {
        "categories": [{"id": c.id, "name": c.name, "description": c.description} for c in cats]
    }


# -- get_my_orders --
def get_my_orders(customer, args):
    """List the customer's recent orders."""
    orders = Order.objects.filter(customer=customer).select_related("pharmacy")[:10]
    result = []
    for o in orders:
        result.append({
            "id": o.id,
            "status": o.status,
            "total": float(o.total),
            "pharmacy": o.pharmacy.business_name if o.pharmacy else "",
            "items_count": o.items.count(),
            "created_at": o.created_at.isoformat(),
            "payment_method": o.payment_method,
        })
    return {"orders": result, "count": len(result)}


# -- get_order_status --
def get_order_status(customer, args):
    """Get the status and details of a specific order."""
    order_id = args.get("order_id")
    try:
        o = Order.objects.select_related("pharmacy", "delivery_address").get(
            id=order_id, customer=customer
        )
    except Order.DoesNotExist:
        return {"error": f"Order #{order_id} not found."}
    items = [
        {"medicine": i.medicine.name, "quantity": i.quantity, "unit_price": float(i.unit_price)}
        for i in o.items.select_related("medicine")
    ]
    history = [
        {"status": h.status, "time": h.created_at.isoformat(), "note": h.note}
        for h in o.status_history.all()
    ]
    return {
        "id": o.id,
        "status": o.status,
        "total": float(o.total),
        "subtotal": float(o.subtotal),
        "delivery_fee": float(o.delivery_fee),
        "payment_method": o.payment_method,
        "is_paid": o.is_paid,
        "pharmacy": o.pharmacy.business_name if o.pharmacy else "",
        "address": f"{o.delivery_address.address_line}, {o.delivery_address.city}" if o.delivery_address else "No address",
        "items": items,
        "status_history": history,
    }


# -- get_my_addresses --
def get_my_addresses(customer, args):
    """List the customer's saved addresses."""
    addrs = Address.objects.filter(customer=customer)
    return {
        "addresses": [
            {
                "id": a.id,
                "label": a.label,
                "address_line": a.address_line,
                "city": a.city,
                "is_default": a.is_default,
            }
            for a in addrs
        ]
    }


# -- prepare_order --
def prepare_order(customer, args):
    """Build an order preview without actually placing it. Returns summary for user confirmation."""
    cart = _cart_for(customer)
    if not cart.items.exists():
        return {"error": "Cart is empty. Add some medicines first."}
    ph = _pharmacy(customer)
    if not ph:
        return {"error": "No pharmacy available. Please select a pharmacy first."}

    # Determine address
    address_id = args.get("address_id")
    if address_id:
        try:
            address = Address.objects.get(id=address_id, customer=customer)
        except Address.DoesNotExist:
            return {"error": f"Address #{address_id} not found."}
    else:
        address = Address.objects.filter(customer=customer, is_default=True).first()
        if not address:
            address = Address.objects.filter(customer=customer).first()
        if not address:
            return {"error": "No delivery address saved. Please add an address first."}

    payment_method = args.get("payment_method", "cod")
    items = []
    subtotal = 0
    for ci in cart.items.select_related("medicine"):
        inv = InventoryItem.objects.filter(pharmacy=ph, medicine=ci.medicine).first()
        price = float(inv.selling_price) if inv else 0
        if inv and inv.quantity_in_stock < ci.quantity:
            return {"error": f"Insufficient stock for {ci.medicine.name}. Only {inv.quantity_in_stock} available."}
        line_total = price * ci.quantity
        subtotal += line_total
        items.append({
            "medicine_id": ci.medicine_id,
            "medicine_name": ci.medicine.name,
            "strength": ci.medicine.strength,
            "quantity": ci.quantity,
            "unit_price": price,
            "line_total": line_total,
        })

    return {
        "ready": True,
        "pharmacy": ph.business_name,
        "address": f"{address.label}: {address.address_line}, {address.city}",
        "address_id": address.id,
        "payment_method": payment_method,
        "items": items,
        "subtotal": subtotal,
        "requires_confirmation": True,
    }


# -- confirm_place_order --
def confirm_place_order(customer, args):
    """Actually place the order after user confirms. Reuses the existing service."""
    from apps.customer.services import place_order_from_cart

    cart = _cart_for(customer)
    address_id = args.get("address_id")
    payment_method = args.get("payment_method", "cod")

    if address_id:
        try:
            address = Address.objects.get(id=address_id, customer=customer)
        except Address.DoesNotExist:
            return {"error": f"Address #{address_id} not found."}
    else:
        address = Address.objects.filter(customer=customer, is_default=True).first()
        if not address:
            address = Address.objects.filter(customer=customer).first()
        if not address:
            return {"error": "No delivery address available."}

    try:
        order = place_order_from_cart(cart, address, payment_method)
    except ValueError as e:
        return {"error": str(e)}

    return {
        "success": True,
        "order_id": order.id,
        "total": float(order.total),
        "status": order.status,
        "message": f"Order #{order.id} placed successfully!",
    }


# -- get_user_profile --
def get_user_profile(customer, args):
    """Get the customer's profile information."""
    user = customer.user
    return {
        "username": user.username,
        "email": user.email,
        "phone": user.phone_number,
        "phone_verified": user.phone_verified,
        "wallet_balance": float(customer.wallet_balance),
        "preferred_language": customer.preferred_language,
        "date_of_birth": str(customer.date_of_birth) if customer.date_of_birth else "",
    }


# -- symptom_check (delegates to the local triage knowledge base) --
def _symptom_check(customer, args):
    from .symptom_check import symptom_check as _run
    return _run(customer, args)


# -- Tool registry --
TOOL_FUNCTIONS = {
    "search_medicines": search_medicines,
    "symptom_check": _symptom_check,
    "get_medicine_details": get_medicine_details,
    "add_to_cart": add_to_cart,
    "get_cart": get_cart,
    "remove_from_cart": remove_from_cart,
    "get_categories": get_categories,
    "get_my_orders": get_my_orders,
    "get_order_status": get_order_status,
    "get_my_addresses": get_my_addresses,
    "prepare_order": prepare_order,
    "confirm_place_order": confirm_place_order,
    "get_user_profile": get_user_profile,
}


def execute_tool(name, customer, args):
    """Execute a tool by name and return the result dict."""
    fn = TOOL_FUNCTIONS.get(name)
    if not fn:
        return {"error": f"Unknown tool: {name}"}
    try:
        return fn(customer, args)
    except Exception as e:
        return {"error": f"Tool execution failed: {str(e)}"}
