from django.contrib import admin

from .models import Address, Cart, CartItem, CustomerProfile, Prescription, PrescriptionItem


class AddressInline(admin.TabularInline):
    model = Address
    extra = 0


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "wallet_balance", "preferred_language"]
    inlines = [AddressInline]


class PrescriptionItemInline(admin.TabularInline):
    model = PrescriptionItem
    extra = 0


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ["id", "customer", "status", "created_at"]
    list_filter = ["status"]
    inlines = [PrescriptionItemInline]


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ["customer", "pharmacy", "updated_at"]
    inlines = [CartItemInline]
