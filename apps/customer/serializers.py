from rest_framework import serializers

from apps.catalog.serializers import MedicineSerializer

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

    class Meta:
        model = Prescription
        fields = "__all__"
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
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ["id", "medicine", "medicine_id", "quantity", "line_total"]

    def get_line_total(self, obj):
        inv = obj.cart.pharmacy and obj.cart.pharmacy.inventory_items.filter(medicine=obj.medicine).first()
        price = inv.selling_price if inv else 0
        return price * obj.quantity


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)

    class Meta:
        model = Cart
        fields = ["id", "customer", "pharmacy", "prescription", "coupon_code", "items", "updated_at"]
        read_only_fields = ["customer"]


class PlaceOrderSerializer(serializers.Serializer):
    address_id = serializers.IntegerField()
    payment_method = serializers.ChoiceField(choices=["cod", "card", "jazzcash", "easypaisa", "wallet"])
