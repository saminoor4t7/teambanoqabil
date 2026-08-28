from decimal import Decimal

from django.conf import settings
from rest_framework import serializers

from apps.catalog.serializers import MedicineSerializer
from apps.medical_store.models import PharmacyProfile

from .models import Address, Cart, CartItem, CustomerProfile, Prescription, PrescriptionItem


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = "__all__"
        read_only_fields = ["customer"]


class CustomerProfileSerializer(serializers.ModelSerializer):
    addresses = AddressSerializer(many=True, read_only=True)

    class Meta:
        model = CustomerProfile
        fields = ["id", "user", "date_of_birth", "wallet_balance", "preferred_language", "addresses"]
        read_only_fields = ["user", "wallet_balance"]


class PrescriptionItemSerializer(serializers.ModelSerializer):
    medicine = MedicineSerializer(read_only=True)

    class Meta:
        model = PrescriptionItem
        fields = "__all__"


class PrescriptionSerializer(serializers.ModelSerializer):
    items = PrescriptionItemSerializer(many=True, read_only=True)
    pharmacy_id = serializers.PrimaryKeyRelatedField(
        source="pharmacy",
        queryset=PharmacyProfile.objects.filter(is_verified=True, is_open=True),
        required=False,
    )
    pharmacy_name = serializers.CharField(source="pharmacy.business_name", read_only=True)
    customer_name = serializers.CharField(source="customer.__str__", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    source_display = serializers.CharField(source="get_source_display", read_only=True)
    reviewed_by_name = serializers.SerializerMethodField()

    def get_reviewed_by_name(self, obj):
        return obj.reviewed_by.get_username() if obj.reviewed_by else None

    class Meta:
        model = Prescription
        fields = [
            "id", "customer", "customer_name", "pharmacy", "pharmacy_id", "pharmacy_name", "file", "source", "source_display",
            "status", "status_display", "doctor_name", "patient_name", "ai_raw_response",
            "ai_model_version", "reviewed_by", "reviewed_by_name", "reviewed_at",
            "rejection_reason", "created_at", "items",
        ]
        read_only_fields = [
            "customer", "status", "ai_raw_response", "ai_model_version",
            "reviewed_by", "reviewed_at", "rejection_reason",
        ]


class CartItemSerializer(serializers.ModelSerializer):
    medicine = MedicineSerializer(read_only=True)
    medicine_id = serializers.PrimaryKeyRelatedField(
        queryset=CartItem._meta.get_field("medicine").related_model.objects.all(),
        source="medicine", write_only=True,
    )
    price = serializers.SerializerMethodField()
    discount_percentage = serializers.SerializerMethodField()
    discount_amount = serializers.SerializerMethodField()
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            "id", "medicine", "medicine_id", "quantity", "price", "discount_percentage",
            "discount_amount", "line_total",
        ]

    def _inventory(self, obj):
        return obj.cart.pharmacy and obj.cart.pharmacy.inventory_items.filter(medicine=obj.medicine).first()

    def get_price(self, obj):
        inventory = self._inventory(obj)
        return inventory.selling_price if inventory else 0

    def get_discount_percentage(self, obj):
        inventory = self._inventory(obj)
        return inventory.discount_percentage if inventory else 0

    def get_discount_amount(self, obj):
        inventory = self._inventory(obj)
        if not inventory:
            return 0
        return (inventory.selling_price * inventory.discount_percentage / 100) * obj.quantity

    def get_line_total(self, obj):
        inventory = self._inventory(obj)
        if not inventory:
            return 0
        discounted_price = inventory.selling_price * (1 - inventory.discount_percentage / 100)
        return discounted_price * obj.quantity


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    subtotal = serializers.SerializerMethodField()
    discount_total = serializers.SerializerMethodField()
    delivery_fee = serializers.SerializerMethodField()
    grand_total = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            "id", "customer", "pharmacy", "prescription", "coupon_code", "items",
            "subtotal", "discount_total", "delivery_fee", "grand_total", "updated_at",
        ]
        read_only_fields = ["customer"]

    def _totals(self, obj):
        subtotal = Decimal("0")
        discount_total = Decimal("0")
        for item in obj.items.select_related("medicine"):
            inventory = (
                obj.pharmacy.inventory_items.filter(medicine=item.medicine).first()
                if obj.pharmacy else None
            )
            if inventory:
                subtotal += inventory.selling_price * item.quantity
                discount_total += (
                    inventory.selling_price * inventory.discount_percentage / 100
                ) * item.quantity
        return subtotal, discount_total

    def get_subtotal(self, obj):
        return self._totals(obj)[0]

    def get_discount_total(self, obj):
        return self._totals(obj)[1]

    def get_delivery_fee(self, obj):
        return Decimal(str(settings.DELIVERY_FEE))

    def get_grand_total(self, obj):
        subtotal, discount_total = self._totals(obj)
        return subtotal - discount_total + Decimal(str(settings.DELIVERY_FEE))


class PlaceOrderSerializer(serializers.Serializer):
    address_id = serializers.IntegerField()
    payment_method = serializers.ChoiceField(choices=["cod", "card", "jazzcash", "easypaisa", "wallet"])
