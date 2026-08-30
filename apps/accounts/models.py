from django.contrib.auth.models import AbstractUser
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import models


class Role(models.TextChoices):
    CUSTOMER = "customer", "Customer"
    PHARMACY = "pharmacy", "Pharmacy / Medical Store"
    RIDER = "rider", "Rider"
    SUPPORT = "support", "Support Agent"
    ADMIN = "admin", "Admin"


class User(AbstractUser):
    """
    Single identity for the whole platform. `customer`, `medical_store`
    and `rider` apps each attach a 1:1 profile to this model instead of
    keeping their own auth tables — this is what lets the three apps
    reference "the same person" consistently (e.g. Order.customer,
    Order.pharmacy, Delivery.rider all ultimately point back to a User).
    """

    username = models.CharField(
        max_length=150,
        validators=[UnicodeUsernameValidator()],
        error_messages={"unique": "A user with that username already exists for this role."},
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    phone_number = models.CharField(max_length=20)
    phone_verified = models.BooleanField(default=False)
    is_active_on_platform = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "id"
    REQUIRED_FIELDS = ["username", "email", "role", "phone_number"]

    def __str__(self):
        return f"{self.username} ({self.role})"

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["username", "role"], name="unique_user_username_per_role"),
            models.UniqueConstraint(fields=["email", "role"], name="unique_user_email_per_role"),
            models.UniqueConstraint(fields=["phone_number", "role"], name="unique_user_phone_per_role"),
        ]


class PendingRegistration(models.Model):
    """Temporary registration data; it becomes a User only after OTP verification."""

    username = models.CharField(max_length=150)
    email = models.EmailField()
    password_hash = models.CharField(max_length=128)
    role = models.CharField(max_length=20, choices=Role.choices)
    phone_number = models.CharField(max_length=20)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    otp_code = models.CharField(max_length=6)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Pending registration for {self.email}"

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["username", "role"], name="unique_pending_username_per_role"),
            models.UniqueConstraint(fields=["email", "role"], name="unique_pending_email_per_role"),
            models.UniqueConstraint(fields=["phone_number", "role"], name="unique_pending_phone_per_role"),
        ]


class AuditLog(models.Model):
    """FR-19: audit sensitive actions & AI outputs used across all apps."""

    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=50, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} by {self.actor} @ {self.created_at}"
