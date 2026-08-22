from django.contrib import admin

from .models import Delivery, Order, OrderItem, OrderStatusHistory, Refund


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


class StatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ["status", "changed_by", "note", "created_at"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "customer", "pharmacy", "status", "total", "is_paid", "created_at"]
    list_filter = ["status", "payment_method", "is_paid"]
    inlines = [OrderItemInline, StatusHistoryInline]


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ["order", "rider", "assigned_at", "picked_up_at", "delivered_at"]


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ["order", "amount", "status", "created_at"]
    list_filter = ["status"]
