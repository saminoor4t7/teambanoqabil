from django.db import models


class OrderStatus(models.TextChoices):
    """FR-10: Pending -> Under Review -> Accepted -> Preparing ->
    Ready for Pickup -> Picked Up -> On the Way -> Delivered
    (plus Cancelled as a terminal escape hatch)."""

    PENDING = "pending", "Pending"
    UNDER_REVIEW = "under_review", "Under Review"
    ACCEPTED = "accepted", "Accepted"
    PREPARING = "preparing", "Preparing"
    READY_FOR_PICKUP = "ready_for_pickup", "Ready for Pickup"
    PICKED_UP = "picked_up", "Picked Up"
    ON_THE_WAY = "on_the_way", "On the Way"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"


class Order(models.Model):
    """
    The interconnection hub between the three role apps: it points at a
    CustomerProfile, a PharmacyProfile and (once dispatched) a
    RiderProfile. None of the three apps needs to import the others'
    models directly — they only ever talk through Order/Delivery, which
    keeps `customer`, `medical_store` and `rider` loosely coupled.
    """

    customer = models.ForeignKey(
        "customer.CustomerProfile", on_delete=models.PROTECT, related_name="orders"
    )
    pharmacy = models.ForeignKey(
        "medical_store.PharmacyProfile", on_delete=models.PROTECT, related_name="orders"
    )
    prescription = models.ForeignKey(
        "customer.Prescription", null=True, blank=True, on_delete=models.SET_NULL, related_name="orders"
    )
    delivery_address = models.ForeignKey(
        "customer.Address", null=True, blank=True, on_delete=models.SET_NULL
    )
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    payment_method = models.CharField(
        max_length=20,
        choices=[("cod", "Cash on Delivery"), ("card", "Card"), ("jazzcash", "JazzCash"),
                 ("easypaisa", "Easypaisa"), ("wallet", "Wallet")],
        default="cod",
    )
    is_paid = models.BooleanField(default=False)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    coupon_code = models.CharField(max_length=30, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status"])]

    def recalc_total(self):
        self.subtotal = sum(item.line_total for item in self.items.all())
        self.total = self.subtotal + self.delivery_fee - self.discount
        self.save(update_fields=["subtotal", "total"])

    def set_status(self, new_status, changed_by=None, note=""):
        self.status = new_status
        self.save(update_fields=["status", "updated_at"])
        OrderStatusHistory.objects.create(order=self, status=new_status, changed_by=changed_by, note=note)

    def __str__(self):
        return f"Order #{self.id} ({self.status})"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    medicine = models.ForeignKey("catalog.Medicine", on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    # Traceability back to the AI-extracted prescription line, if any (FR-09).
    prescription_item = models.ForeignKey(
        "customer.PrescriptionItem", null=True, blank=True, on_delete=models.SET_NULL
    )

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.medicine} x{self.quantity}"


class OrderStatusHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="status_history")
    status = models.CharField(max_length=20, choices=OrderStatus.choices)
    changed_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class Delivery(models.Model):
    """Owned by the orders hub but written to almost exclusively by the
    rider app (assignment, live location, pickup/delivery confirmation) —
    this is the other half of the customer<->pharmacy<->rider triangle."""

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="delivery")
    rider = models.ForeignKey(
        "rider.RiderProfile", null=True, blank=True, on_delete=models.SET_NULL, related_name="deliveries"
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    eta_minutes_min = models.PositiveIntegerField(null=True, blank=True)
    eta_minutes_max = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return f"Delivery for Order #{self.order_id}"


class Refund(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="refunds")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=[("requested", "Requested"), ("approved", "Approved"), ("rejected", "Rejected")],
        default="requested",
    )
    created_at = models.DateTimeField(auto_now_add=True)
