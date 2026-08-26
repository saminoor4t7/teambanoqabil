from math import asin, cos, radians, sin, sqrt

from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, serializers, status, viewsets
from rest_framework.exceptions import ValidationError

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.customer.models import Prescription
from apps.customer.serializers import PrescriptionSerializer
from apps.orders.models import Order, OrderStatus
from apps.orders.serializers import OrderSerializer

from . import services
from .models import DemandForecast, InventoryItem, PharmacyProfile
from .permissions import IsPharmacy
from .serializers import (
    DemandForecastSerializer,
    InventoryItemSerializer,
    NearbyPharmacySerializer,
    PharmacyProfileSerializer,
    PrescriptionReviewSerializer,
)


def _pharmacy(request):
    return get_object_or_404(PharmacyProfile, user=request.user)


class PharmacyDirectorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PharmacyProfile
        fields = ["id", "business_name", "city", "address_line", "is_open", "is_verified"]


class PharmacyDirectoryView(generics.ListAPIView):
    """Public read-only directory so customers can discover pharmacies."""

    serializer_class = PharmacyDirectorySerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

    def get_queryset(self):
        return PharmacyProfile.objects.filter(is_open=True).order_by("business_name")


class MyPharmacyView(generics.RetrieveUpdateAPIView):
    serializer_class = PharmacyProfileSerializer
    permission_classes = [IsPharmacy]

    def get_object(self):
        profile, _ = PharmacyProfile.objects.get_or_create(
            user=self.request.user,
            defaults={"business_name": self.request.user.username, "license_number": f"TEMP-{self.request.user.id}"},
        )
        return profile


class PharmacyListView(generics.ListAPIView):
    serializer_class = PharmacyProfileSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    queryset = PharmacyProfile.objects.filter(is_verified=True, is_open=True).order_by("business_name")


class PharmacyDetailView(generics.RetrieveAPIView):
    serializer_class = PharmacyProfileSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    queryset = PharmacyProfile.objects.filter(is_verified=True, is_open=True)
    lookup_url_kwarg = "pharmacy_id"


class NearbyPharmacyView(generics.ListAPIView):
    serializer_class = NearbyPharmacySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        latitude = self.request.query_params.get("latitude") or self.request.query_params.get("lat")
        longitude = self.request.query_params.get("longitude") or self.request.query_params.get("lng")
        if latitude is None or longitude is None:
            raise ValidationError({"detail": "latitude and longitude are required."})

        try:
            self.customer_latitude = float(latitude)
            self.customer_longitude = float(longitude)
        except (TypeError, ValueError):
            raise ValidationError({"detail": "latitude and longitude must be valid numbers."})

        if not -90 <= self.customer_latitude <= 90 or not -180 <= self.customer_longitude <= 180:
            raise ValidationError({"detail": "latitude or longitude is outside the valid range."})

        pharmacies = PharmacyProfile.objects.filter(
            is_verified=True, is_open=True,
            latitude__isnull=False, longitude__isnull=False,
        )
        nearby = []
        for pharmacy in pharmacies:
            distance = self._distance_km(
                self.customer_latitude, self.customer_longitude,
                float(pharmacy.latitude), float(pharmacy.longitude),
            )
            if distance <= 10:
                pharmacy.distance_km = round(distance, 2)
                nearby.append(pharmacy)
        return sorted(nearby, key=lambda pharmacy: pharmacy.distance_km)

    @staticmethod
    def _distance_km(latitude_one, longitude_one, latitude_two, longitude_two):
        earth_radius_km = 6371
        latitude_delta = radians(latitude_two - latitude_one)
        longitude_delta = radians(longitude_two - longitude_one)
        value = (
            sin(latitude_delta / 2) ** 2
            + cos(radians(latitude_one))
            * cos(radians(latitude_two))
            * sin(longitude_delta / 2) ** 2
        )
        return earth_radius_km * 2 * asin(sqrt(value))


class InventoryViewSet(viewsets.ModelViewSet):
    serializer_class = InventoryItemSerializer
    permission_classes = [IsPharmacy]

    def get_queryset(self):
        return InventoryItem.objects.filter(pharmacy__user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(pharmacy=_pharmacy(self.request))


class IncomingOrdersView(generics.ListAPIView):
    """Receive and review incoming orders."""

    serializer_class = OrderSerializer
    permission_classes = [IsPharmacy]

    def get_queryset(self):
        return Order.objects.filter(pharmacy__user=self.request.user).exclude(
            status__in=[OrderStatus.DELIVERED, OrderStatus.CANCELLED]
        )


class OrderTransitionView(APIView):
    """POST /api/pharmacy/orders/<id>/<action>/ where action in
    accept|preparing|ready-for-pickup|reject."""

    permission_classes = [IsPharmacy]

    ACTIONS = {
        "accept": services.accept_order,
        "preparing": services.mark_preparing,
        "ready-for-pickup": services.mark_ready_for_pickup,
    }

    def post(self, request, order_id, action):
        order = get_object_or_404(Order, id=order_id, pharmacy__user=request.user)
        if action == "reject":
            order.set_status(OrderStatus.CANCELLED, changed_by=request.user, note="Rejected by pharmacy")
        elif action in self.ACTIONS:
            self.ACTIONS[action](order, request.user)
        else:
            return Response({"detail": "Unknown action."}, status=400)
        return Response(OrderSerializer(order).data)


class VerifyPrescriptionView(APIView):
    """FR-05 + Pharmacist Copilot: approve/reject an AI-extracted prescription."""

    permission_classes = [IsPharmacy]

    def post(self, request, prescription_id):
        prescription = get_object_or_404(
            Prescription, id=prescription_id, pharmacy=_pharmacy(request)
        )
        decision = request.data.get("decision")
        notes = request.data.get("notes", "")
        if decision not in ("approved", "rejected", "needs_info"):
            return Response({"detail": "Invalid decision."}, status=400)
        prescription = services.verify_prescription(prescription, _pharmacy(request), request.user, decision, notes)
        return Response({"prescription_id": prescription.id, "status": prescription.status})


class IncomingPrescriptionsView(generics.ListAPIView):
    serializer_class = PrescriptionSerializer
    permission_classes = [IsPharmacy]

    def get_queryset(self):
        return Prescription.objects.filter(pharmacy__user=self.request.user).order_by("-created_at")


class DemandForecastView(generics.ListAPIView):
    """FR-14: pharmacy dashboard consumes forecasts generated by the AI
    service's scheduled job (G. Inventory Forecasting)."""

    serializer_class = DemandForecastSerializer
    permission_classes = [IsPharmacy]

    def get_queryset(self):
        return DemandForecast.objects.filter(pharmacy__user=self.request.user).order_by("-generated_at")
