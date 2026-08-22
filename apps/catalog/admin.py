from django.contrib import admin

from .models import Brand, Category, Medicine


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name"]


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ["name"]


@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    list_display = ["name", "strength", "brand", "category", "requires_prescription", "is_active"]
    list_filter = ["requires_prescription", "is_active", "category"]
    search_fields = ["name", "generic_name"]
