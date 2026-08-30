from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import AuditLog, PendingRegistration, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    # All account types share this table; role identifies customer, rider,
    # pharmacy, support, or admin accounts.
    list_display = ["username", "email", "role"]
    list_filter = ["role"]
    search_fields = ["username", "email"]
    ordering = ["username"]
    fieldsets = (
        (None, {"fields": ("username", "email")}),
        ("Medical Panda", {"fields": ("role", "phone_number", "phone_verified", "is_active_on_platform")} ),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")} ),
        ("Important dates", {"fields": ("last_login", "date_joined")} ),
    )


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["action", "actor", "target_type", "target_id", "created_at"]
    list_filter = ["action"]
    search_fields = ["target_id", "action"]


@admin.register(PendingRegistration)
class PendingRegistrationAdmin(admin.ModelAdmin):
    list_display = ["username", "email", "role", "phone_number", "expires_at", "created_at"]
    list_filter = ["role", "created_at"]
    search_fields = ["username", "email", "phone_number"]
    readonly_fields = ["password_hash", "otp_code", "created_at"]
