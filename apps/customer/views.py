from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import AuditLog
from apps.medical_store.models import InventoryItem, PharmacyProfile

from . import services
from .models import Address, Cart, CartItem, CustomerProfile, Prescription
from .permissions import IsCustomer
from .serializers import (
    AddressSerializer,
    CartItemSerializer,
    CartSerializer,
    CustomerProfileSerializer,
    PlaceOrderSerializer,
    PrescriptionSerializer,
)


def _profile(request):
    return get_object_or_404(CustomerProfile, user=request.user)


class MyProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = CustomerProfileSerializer
    permission_classes = [IsCustomer]

    def get_object(self):
        profile, _ = CustomerProfile.objects.get_or_create(user=self.request.user)
        return profile


class AddressViewSet(viewsets.ModelViewSet):
    serializer_class = AddressSerializer
    permission_classes = [IsCustomer]

    def get_queryset(self):
        if self.request.user.is_superuser or self.request.user.role == "admin":
            return Address.objects.all()
        return Address.objects.filter(customer__user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(customer=_profile(self.request))


class PrescriptionViewSet(viewsets.ModelViewSet):
    """FR-02 upload, kicks off FR-03 AI extraction asynchronously."""

    serializer_class = PrescriptionSerializer
    permission_classes = [IsCustomer]
    http_method_names = ["get", "post", "head"]

    def get_queryset(self):
        if self.request.user.is_superuser or self.request.user.role == "admin":
            return Prescription.objects.all()
        return Prescription.objects.filter(customer__user=self.request.user)

    def perform_create(self, serializer):
        pharmacy_id = self.request.data.get("pharmacy") or self.request.data.get("pharmacy_id")
        pharmacy = get_object_or_404(
            PharmacyProfile,
            id=pharmacy_id,
            is_verified=True,
            is_open=True,
        )
        prescription = serializer.save(
            customer=_profile(self.request), pharmacy=pharmacy, status="processing"
        )
        AuditLog.objects.create(
            actor=self.request.user, action="prescription_uploaded",
            target_type="Prescription", target_id=str(prescription.id),
        )
        # In production this is dispatched to Celery; called inline here
        # for a runnable demo.
        result = services.request_ai_prescription_extraction(prescription)
        if result:
            prescription.ai_raw_response = result
            prescription.ai_model_version = result.get("model_version", "")
            prescription.doctor_name = result.get("doctor_name", prescription.doctor_name)
            prescription.patient_name = result.get("patient_name", prescription.patient_name)
        # Turn the AI payload (if any) into PrescriptionItem rows right away
        # (B7) so the customer sees extracted items and can build a cart.
        services.parse_ai_extraction_into_items(prescription)
        prescription.status = "needs_review"
        prescription.save()

    def retrieve(self, request, *args, **kwargs):
        prescription = self.get_object()
        services.parse_ai_extraction_into_items(prescription)
        return Response(self.get_serializer(prescription).data)

    @action(detail=True, methods=["post"], url_path="build-cart")
    def build_cart(self, request, pk=None):
        """Convert a prescription's extracted items into the customer's cart."""
        prescription = self.get_object()
        try:
            cart, unmatched = services.build_cart_from_prescription(
                prescription, _profile(request)
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({
            "cart": CartSerializer(cart).data,
            "unmatched": unmatched,
        })


class CartView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        cart, _ = Cart.objects.get_or_create(customer=_profile(request))
        return Response(CartSerializer(cart).data)

    def post(self, request):
        """Add/update a single item: {"medicine_id": 1, "quantity": 2, "pharmacy_id": 3}"""
        cart, _ = Cart.objects.get_or_create(customer=_profile(request))
        pharmacy_id = request.data.get("pharmacy_id") or request.data.get("pharmacy")
        if pharmacy_id:
            pharmacy = get_object_or_404(
                PharmacyProfile, id=pharmacy_id, is_verified=True, is_open=True
            )
            if cart.pharmacy_id != pharmacy.id:
                cart.items.all().delete()
                cart.pharmacy = pharmacy
                cart.save(update_fields=["pharmacy", "updated_at"])

        medicine_id = request.data.get("medicine_id")
        try:
            quantity = int(request.data.get("quantity", 1))
        except (TypeError, ValueError):
            return Response({"detail": "quantity must be a valid integer."}, status=400)
        if quantity < 1:
            return Response({"detail": "Quantity must be at least 1."}, status=400)
        if medicine_id:
            if not cart.pharmacy_id:
                return Response({"detail": "Select a pharmacy before adding medicine."}, status=400)
            from apps.catalog.models import Medicine
            if not Medicine.objects.filter(id=medicine_id, is_active=True).exists():
                return Response({"detail": "Medicine not found."}, status=404)
            inventory = get_object_or_404(
                InventoryItem,
                pharmacy_id=cart.pharmacy_id,
                medicine_id=medicine_id,
            )
            if inventory.selling_price <= 0 or inventory.discount_percentage >= 100:
                return Response({"detail": "This medicine has no valid price at the selected pharmacy."}, status=400)
            if inventory.quantity_in_stock < quantity:
                return Response({"detail": "Requested quantity is not available."}, status=400)
            item, _ = cart.items.get_or_create(medicine_id=medicine_id)
            item.quantity = quantity
            item.save()
        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)

    def delete(self, request):
        """Clear the entire cart."""
        cart, _ = Cart.objects.get_or_create(customer=_profile(request))
        cart.items.all().delete()
        cart.pharmacy = None
        cart.prescription = None
        cart.coupon_code = ""
        cart.save(update_fields=["pharmacy", "prescription", "coupon_code", "updated_at"])
        return Response({"detail": "Cart cleared successfully."}, status=status.HTTP_204_NO_CONTENT)

    def patch(self, request):
        """Update cart attributes (coupon_code, prescription, etc.)."""
        cart, _ = Cart.objects.get_or_create(customer=_profile(request))
        
        # Allow updating coupon_code
        if "coupon_code" in request.data:
            cart.coupon_code = request.data.get("coupon_code", "")
        
        # Allow updating prescription
        if "prescription_id" in request.data:
            prescription_id = request.data.get("prescription_id")
            if prescription_id:
                prescription = get_object_or_404(
                    Prescription, id=prescription_id, customer=_profile(request)
                )
                cart.prescription = prescription
            else:
                cart.prescription = None
        
        cart.save()
        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)


class CartItemViewSet(viewsets.ModelViewSet):
    """ViewSet for managing individual cart items."""
    serializer_class = CartItemSerializer
    permission_classes = [IsCustomer]
    http_method_names = ["get", "delete", "patch", "head"]

    def get_queryset(self):
        profile = _profile(self.request)
        return CartItem.objects.filter(cart__customer=profile)

    def get_object(self):
        """Get the cart item, ensuring it belongs to the current user's cart."""
        item = get_object_or_404(
            CartItem,
            id=self.kwargs.get("pk"),
            cart__customer=_profile(self.request)
        )
        return item

    def destroy(self, request, *args, **kwargs):
        """Delete a specific cart item."""
        item = self.get_object()
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def partial_update(self, request, *args, **kwargs):
        """Update cart item quantity."""
        item = self.get_object()
        quantity = request.data.get("quantity")
        
        if quantity is not None:
            quantity = int(quantity)
            if quantity <= 0:
                item.delete()
                return Response(status=status.HTTP_204_NO_CONTENT)
            
            # Validate stock availability
            cart = item.cart
            if cart.pharmacy:
                inventory = get_object_or_404(
                    InventoryItem,
                    pharmacy_id=cart.pharmacy_id,
                    medicine_id=item.medicine_id,
                )
                if inventory.quantity_in_stock < quantity:
                    return Response(
                        {"detail": "Requested quantity is not available."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            item.quantity = quantity
            item.save()
        
        return Response(CartItemSerializer(item).data, status=status.HTTP_200_OK)


class PlaceOrderView(APIView):
    permission_classes = [IsCustomer]

    def post(self, request):
        serializer = PlaceOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart, _ = Cart.objects.get_or_create(customer=_profile(request))
        address = get_object_or_404(Address, id=serializer.validated_data["address_id"], customer__user=request.user)
        try:
            order = services.place_order_from_cart(cart, address, serializer.validated_data["payment_method"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        from apps.orders.serializers import OrderSerializer
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)
