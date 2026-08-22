from rest_framework import serializers

from apps.catalog.serializers import MedicineSerializer

from .models import Delivery, Order, OrderItem, OrderStatusHistory, Refund


class OrderItemSerializer(serializers.ModelSerializer):
    medicine = MedicineSerializer(read_only=True)
    line_total = serializers.ReadOnlyField()

    class Meta:
        model = OrderItem
        fields = ["id", "medicine", "quantity", "unit_price", "line_total", "prescription_item"]


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusHistory
        fields = ["status", "changed_by", "note", "created_at"]


class DeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = Delivery
        fields = "__all__"


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    delivery = DeliverySerializer(read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "customer", "pharmacy", "prescription", "delivery_address", "status",
            "payment_method", "is_paid", "subtotal", "delivery_fee", "discount", "total",
            "coupon_code", "items", "status_history", "delivery", "created_at", "updated_at",
        ]
        read_only_fields = [f.name for f in Order._meta.fields if f.name != "id"]


class RefundSerializer(serializers.ModelSerializer):
    class Meta:
        model = Refund
        fields = "__all__"
        read_only_fields = ["status", "created_at"]
