from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import AuditLog

from . import services
from .models import Address, Cart, CustomerProfile, Prescription
from .permissions import IsCustomer
from .serializers import (
    AddressSerializer,
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
        return Address.objects.filter(customer__user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(customer=_profile(self.request))


class PrescriptionViewSet(viewsets.ModelViewSet):
    """FR-02 upload, kicks off FR-03 AI extraction asynchronously."""

    serializer_class = PrescriptionSerializer
    permission_classes = [IsCustomer]
    http_method_names = ["get", "post", "head"]

    def get_queryset(self):
        return Prescription.objects.filter(customer__user=self.request.user)

    def perform_create(self, serializer):
        prescription = serializer.save(customer=_profile(self.request), status="processing")
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
        prescription.status = "needs_review"
        prescription.save()


class CartView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        cart, _ = Cart.objects.get_or_create(customer=_profile(request))
        return Response(CartSerializer(cart).data)

    def post(self, request):
        """Add/update a single item: {"medicine_id": 1, "quantity": 2, "pharmacy_id": 3}"""
        cart, _ = Cart.objects.get_or_create(customer=_profile(request))
        pharmacy_id = request.data.get("pharmacy_id")
        if pharmacy_id:
            cart.pharmacy_id = pharmacy_id
            cart.save(update_fields=["pharmacy"])

        medicine_id = request.data.get("medicine_id")
        quantity = int(request.data.get("quantity", 1))
        if medicine_id:
            item, _ = cart.items.get_or_create(medicine_id=medicine_id)
            item.quantity = quantity
            item.save()
        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)


class BuildCartFromPrescriptionView(APIView):
    """FR-09: prescription -> suggested cart."""

    permission_classes = [IsCustomer]

    def post(self, request, prescription_id):
        prescription = get_object_or_404(Prescription, id=prescription_id, customer__user=request.user)
        cart, _ = Cart.objects.get_or_create(customer=_profile(request))
        services.build_cart_from_prescription(cart, prescription)
        return Response(CartSerializer(cart).data)


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
