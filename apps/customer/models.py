from django.conf import settings
from django.db import models


class CustomerProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="customer_profile")
    date_of_birth = models.DateField(null=True, blank=True)
    wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    preferred_language = models.CharField(
        max_length=15,
        choices=[("en", "English"), ("ur", "Urdu"), ("roman_ur", "Roman Urdu")],
        default="en",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Customer: {self.user.username}"


class Address(models.Model):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=50, default="Home")
    address_line = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_default = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.label} - {self.city}"


class Prescription(models.Model):
    """FR-02/03/04/05: uploaded prescription + AI extraction + pharmacist
    verification state, all tracked on one record for audit purposes."""

    STATUS_CHOICES = [
        ("uploaded", "Uploaded"),
        ("processing", "AI Processing"),
        ("needs_review", "Needs Pharmacist Review"),
        ("verified", "Verified"),
        ("rejected", "Rejected"),
    ]

    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name="prescriptions")
    file = models.FileField(upload_to="prescriptions/%Y/%m/")
    source = models.CharField(
        max_length=20, choices=[("camera", "Camera"), ("gallery", "Gallery"), ("pdf", "PDF")], default="camera"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="uploaded")
    doctor_name = models.CharField(max_length=150, blank=True)
    patient_name = models.CharField(max_length=150, blank=True)
    ai_raw_response = models.JSONField(null=True, blank=True)  # full AIExtraction payload
    ai_model_version = models.CharField(max_length=50, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Prescription #{self.id} ({self.status})"


class PrescriptionItem(models.Model):
    """One AI-extracted (or pharmacist-corrected) medicine line: FR-03/04.
    `medicine` stays null until matching + human confirmation resolve it
    to a real catalog entry (FR-06)."""

    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE, related_name="items")
    raw_medicine_text = models.CharField(max_length=255)  # as read by OCR
    medicine = models.ForeignKey(
        "catalog.Medicine", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    strength = models.CharField(max_length=50, blank=True)
    dosage = models.CharField(max_length=100, blank=True)
    frequency = models.CharField(max_length=100, blank=True)
    duration = models.CharField(max_length=100, blank=True)
    quantity = models.PositiveIntegerField(null=True, blank=True)
    special_instructions = models.CharField(max_length=255, blank=True)
    confidence = models.FloatField(null=True, blank=True)  # FR-04
    is_ambiguous = models.BooleanField(default=False)
    pharmacist_confirmed = models.BooleanField(default=False)

    def __str__(self):
        return self.raw_medicine_text


class Cart(models.Model):
    customer = models.OneToOneField(CustomerProfile, on_delete=models.CASCADE, related_name="cart")
    pharmacy = models.ForeignKey(
        "medical_store.PharmacyProfile", null=True, blank=True, on_delete=models.SET_NULL
    )
    prescription = models.ForeignKey(Prescription, null=True, blank=True, on_delete=models.SET_NULL)
    coupon_code = models.CharField(max_length=30, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart({self.customer})"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    medicine = models.ForeignKey("catalog.Medicine", on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ("cart", "medicine")
