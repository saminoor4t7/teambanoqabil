from django.conf import settings
from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator


class PharmacyProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pharmacy_profile")
    business_name = models.CharField(max_length=200)
    license_number = models.CharField(max_length=100, unique=True)
    address_line = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_verified = models.BooleanField(default=False)  # admin approves new pharmacies
    is_open = models.BooleanField(default=True)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.business_name


class InventoryItem(models.Model):
    pharmacy = models.ForeignKey(PharmacyProfile, on_delete=models.CASCADE, related_name="inventory_items")
    medicine = models.ForeignKey("catalog.Medicine", on_delete=models.CASCADE, related_name="inventory_items")
    quantity_in_stock = models.PositiveIntegerField(default=0)
    reorder_threshold = models.PositiveIntegerField(default=10)  # feeds low-stock visibility (FR-13)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("pharmacy", "medicine")

    @property
    def is_low_stock(self):
        return self.quantity_in_stock <= self.reorder_threshold

    def __str__(self):
        return f"{self.medicine} @ {self.pharmacy} ({self.quantity_in_stock})"


class PrescriptionReview(models.Model):
    """FR-05 human verification + F. Pharmacist Copilot audit trail —
    kept in this app (not `customer`) because it's pharmacy-side work,
    but it points back at the customer app's Prescription record."""

    prescription = models.ForeignKey(
        "customer.Prescription", on_delete=models.CASCADE, related_name="reviews"
    )
    pharmacy = models.ForeignKey(PharmacyProfile, on_delete=models.CASCADE, related_name="prescription_reviews")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    decision = models.CharField(
        max_length=20, choices=[("approved", "Approved"), ("rejected", "Rejected"), ("needs_info", "Needs Info")]
    )
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class DemandForecast(models.Model):
    """G. Inventory Forecasting output surfaced on the pharmacy dashboard
    (FR-14) — populated by a scheduled job in the AI service, written
    here for pharmacists/admin to review."""

    pharmacy = models.ForeignKey(PharmacyProfile, on_delete=models.CASCADE, related_name="forecasts")
    medicine = models.ForeignKey("catalog.Medicine", on_delete=models.CASCADE)
    current_stock = models.PositiveIntegerField()
    expected_demand = models.PositiveIntegerField()
    recommended_restock = models.PositiveIntegerField()
    generated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Forecast {self.medicine} @ {self.pharmacy}"
