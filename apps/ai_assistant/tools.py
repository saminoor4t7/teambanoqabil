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
def search_medicines(customer, args):
    """Search medicines by name, generic name, or category name."""
    query = args.get("query", "").strip()
    category = args.get("category", "").strip()
    qs = Medicine.objects.filter(is_active=True)
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(generic_name__icontains=query))
    if category:
        qs = qs.filter(category__name__icontains=category)
    results = qs[:15]
    medicines = []
    for m in results:
        medicines.append({
            "id": m.id,
            "name": m.name,
            "generic_name": m.generic_name,
            "strength": m.strength,
            "form": m.form,
            "requires_prescription": m.requires_prescription,
            "description": m.description[:120] if m.description else "",
        })
    return {"found": len(medicines), "medicines": medicines}


# -- get_medicine_details --
def get_medicine_details(customer, args):
    """Get full details about a specific medicine by ID."""
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
            stock = inv.quantity_in_stock
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
        "pharmacy": ph.business_name if ph else "No pharmacy selected",
    }


# -- add_to_cart --
def add_to_cart(customer, args):
    """Add a medicine to the customer's cart."""
    medicine_id = args.get("medicine_id")
    quantity = int(args.get("quantity", 1))
    try:
        medicine = Medicine.objects.get(id=medicine_id, is_active=True)
    except Medicine.DoesNotExist:
        return {"error": f"Medicine #{medicine_id} not found."}
    cart = _cart_for(customer)
    ph = _pharmacy(customer)
    if ph and not cart.pharmacy_id:
        cart.pharmacy = ph
        cart.save(update_fields=["pharmacy"])
    item, created = cart.items.get_or_create(medicine=medicine)
    item.quantity = quantity
    item.save()
    return {
        "success": True,
        "message": f"{medicine.name} (qty {quantity}) added to cart.",
        "medicine": {"id": medicine.id, "name": medicine.name, "strength": medicine.strength},
        "quantity": quantity,
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


# -- Tool registry --
TOOL_FUNCTIONS = {
    "search_medicines": search_medicines,
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
