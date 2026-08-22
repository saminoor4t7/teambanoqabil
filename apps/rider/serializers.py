from rest_framework import serializers

from .models import DeliveryOffer, RiderLocationPing, RiderProfile


class RiderProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiderProfile
        fields = "__all__"
        read_only_fields = ["user", "is_verified", "wallet_balance", "rating"]


class RiderLocationPingSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiderLocationPing
        fields = "__all__"
        read_only_fields = ["rider"]


class DeliveryOfferSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryOffer
        fields = "__all__"
