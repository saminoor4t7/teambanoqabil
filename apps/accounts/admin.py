from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import AuditLog, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["username", "email", "role", "phone_number", "phone_verified", "is_active"]
    list_filter = ["role", "phone_verified", "is_active"]
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Medical Panda", {"fields": ("role", "phone_number", "phone_verified", "is_active_on_platform")}),
    )


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["action", "actor", "target_type", "target_id", "created_at"]
    list_filter = ["action"]
    search_fields = ["target_id", "action"]
