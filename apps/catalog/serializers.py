from rest_framework import serializers

from apps.medical_store.models import InventoryItem

from .models import Brand, Category, Medicine


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = "__all__"


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = "__all__"


class MedicineSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)
    price = serializers.SerializerMethodField()
    discount_percentage = serializers.SerializerMethodField()
    quantity_in_stock = serializers.SerializerMethodField()

    class Meta:
        model = Medicine
        fields = [
            "id", "name", "generic_name", "strength", "form", "category", "brand",
            "requires_prescription", "description", "image", "is_active", "created_at",
            "price", "discount_percentage", "quantity_in_stock",
        ]

    def _inventory_for_request(self, obj):
        request = self.context.get("request") if self.context else None
        pharmacy_id = request.query_params.get("pharmacy_id") if request is not None else None

        if pharmacy_id:
            return InventoryItem.objects.filter(medicine=obj, pharmacy_id=pharmacy_id).first()

        return (
            InventoryItem.objects.filter(
                medicine=obj,
                pharmacy__is_verified=True,
                pharmacy__is_open=True,
            )
            .order_by("selling_price", "-quantity_in_stock")
            .first()
        )

    def get_price(self, obj):
        inventory = self._inventory_for_request(obj)
        return float(inventory.selling_price) if inventory else 0

    def get_discount_percentage(self, obj):
        inventory = self._inventory_for_request(obj)
        return float(inventory.discount_percentage) if inventory else 0

    def get_quantity_in_stock(self, obj):
        inventory = self._inventory_for_request(obj)
        return inventory.quantity_in_stock if inventory else 0
