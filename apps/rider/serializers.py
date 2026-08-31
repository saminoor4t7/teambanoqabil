from rest_framework import serializers

from apps.accounts.serializers import UserSerializer

from .models import DeliveryOffer, RiderLocationPing, RiderProfile


class RiderProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = RiderProfile
        fields = "__all__"
        read_only_fields = ["is_verified", "wallet_balance", "rating"]


class RiderLocationPingSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiderLocationPing
        fields = "__all__"
        read_only_fields = ["rider"]


class DeliveryOfferSerializer(serializers.ModelSerializer):
    order_id = serializers.IntegerField(source="delivery.order_id", read_only=True)
    order_status = serializers.CharField(source="delivery.order.status", read_only=True)
    pharmacy_name = serializers.CharField(source="delivery.order.pharmacy.business_name", read_only=True)
    pharmacy_address = serializers.SerializerMethodField()
    pharmacy_latitude = serializers.SerializerMethodField()
    pharmacy_longitude = serializers.SerializerMethodField()
    customer_name = serializers.CharField(source="delivery.order.customer.user.username", read_only=True)
    customer_phone = serializers.CharField(source="delivery.order.customer.user.phone_number", read_only=True)
    drop_address = serializers.SerializerMethodField()
    drop_latitude = serializers.SerializerMethodField()
    drop_longitude = serializers.SerializerMethodField()
    total = serializers.DecimalField(
        source="delivery.order.total", max_digits=10, decimal_places=2, read_only=True
    )
    payment_method = serializers.CharField(source="delivery.order.payment_method", read_only=True)

    class Meta:
        model = DeliveryOffer
        fields = "__all__"

    def _order(self, obj):
        return obj.delivery.order

    def get_pharmacy_address(self, obj):
        pharmacy = self._order(obj).pharmacy
        return ", ".join(filter(None, [pharmacy.address_line, pharmacy.city]))

    def get_pharmacy_latitude(self, obj):
        return obj.delivery.order.pharmacy.latitude

    def get_pharmacy_longitude(self, obj):
        return obj.delivery.order.pharmacy.longitude

    def get_drop_address(self, obj):
        address = self._order(obj).delivery_address
        if not address:
            return None
        return ", ".join(filter(None, [address.address_line, address.city]))

    def get_drop_latitude(self, obj):
        address = self._order(obj).delivery_address
        return address.latitude if address else None

    def get_drop_longitude(self, obj):
        address = self._order(obj).delivery_address
        return address.longitude if address else None
