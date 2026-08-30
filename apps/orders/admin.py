from django.contrib import admin

from .models import Delivery, Order, OrderItem, OrderStatusHistory, Refund


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["line_total"]

    @admin.display(description="Line total")
    def line_total(self, obj):
        return obj.line_total


class StatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ["status", "changed_by", "note", "created_at"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "customer", "pharmacy", "status", "total", "is_paid", "created_at"]
    list_filter = ["pharmacy", "status", "payment_method", "is_paid", "created_at"]
    search_fields = ["=id", "customer__user__username", "customer__user__email", "pharmacy__business_name"]
    readonly_fields = ["subtotal", "delivery_fee", "discount", "total", "created_at", "updated_at"]
    inlines = [OrderItemInline, StatusHistoryInline]


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ["order", "rider", "assigned_at", "picked_up_at", "delivered_at"]


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ["order", "amount", "status", "created_at"]
    list_filter = ["status"]
