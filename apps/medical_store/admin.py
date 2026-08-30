from django.contrib import admin

from .models import DemandForecast, InventoryItem, PharmacyProfile, PrescriptionReview


@admin.register(PharmacyProfile)
class PharmacyProfileAdmin(admin.ModelAdmin):
    list_display = ["business_name", "city", "is_verified", "is_open", "rating"]
    list_filter = ["is_verified", "is_open", "city"]


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = [
        "pharmacy", "medicine", "quantity_in_stock", "reorder_threshold", "selling_price",
        "discount_percentage",
    ]
    list_filter = ["pharmacy"]


@admin.register(PrescriptionReview)
class PrescriptionReviewAdmin(admin.ModelAdmin):
    list_display = ["prescription", "pharmacy", "decision", "reviewed_by", "created_at"]
    list_filter = ["decision"]


@admin.register(DemandForecast)
class DemandForecastAdmin(admin.ModelAdmin):
    list_display = ["pharmacy", "medicine", "current_stock", "expected_demand", "recommended_restock"]
