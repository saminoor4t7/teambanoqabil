from rest_framework import serializers

from apps.catalog.serializers import MedicineSerializer
from apps.customer.serializers import PrescriptionSerializer

from .models import DemandForecast, InventoryItem, PharmacyProfile, PrescriptionReview


class PharmacyProfileSerializer(serializers.ModelSerializer):
    pharmacy_id = serializers.IntegerField(source="pk", read_only=True)

    class Meta:
        model = PharmacyProfile
        fields = [
            "pharmacy_id", "id", "user", "business_name", "license_number", "address_line",
            "city", "latitude", "longitude", "is_verified", "is_open", "rating", "created_at",
        ]
        read_only_fields = ["user", "is_verified", "rating"]


class NearbyPharmacySerializer(PharmacyProfileSerializer):
    distance_km = serializers.FloatField(read_only=True)

    class Meta(PharmacyProfileSerializer.Meta):
        fields = PharmacyProfileSerializer.Meta.fields + ["distance_km"]


class InventoryItemSerializer(serializers.ModelSerializer):
    medicine = MedicineSerializer(read_only=True)
    medicine_id = serializers.PrimaryKeyRelatedField(
        queryset=InventoryItem._meta.get_field("medicine").related_model.objects.all(),
        source="medicine", write_only=True,
    )
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = InventoryItem
        fields = ["id", "pharmacy", "medicine", "medicine_id", "quantity_in_stock",
                  "reorder_threshold", "selling_price", "is_low_stock", "updated_at"]
        read_only_fields = ["pharmacy"]


class PrescriptionReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrescriptionReview
        fields = "__all__"
        read_only_fields = ["pharmacy", "reviewed_by", "created_at"]


class DemandForecastSerializer(serializers.ModelSerializer):
    medicine = MedicineSerializer(read_only=True)

    class Meta:
        model = DemandForecast
        fields = "__all__"
