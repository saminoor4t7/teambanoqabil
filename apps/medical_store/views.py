import json
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


def _distance_km(latitude_one, longitude_one, latitude_two, longitude_two):
    """Great-circle (Haversine) distance in kilometres between two coordinate pairs."""
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
        return PharmacyProfile.objects.filter(is_verified=True, is_open=True).order_by("business_name")


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


class CustomerInventoryView(generics.ListAPIView):
    serializer_class = InventoryItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return InventoryItem.objects.filter(
            pharmacy_id=self.kwargs["pharmacy_id"],
            pharmacy__is_verified=True,
            pharmacy__is_open=True,
            medicine__is_active=True,
        ).select_related("medicine", "medicine__category", "medicine__brand")


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
            distance = _distance_km(
                self.customer_latitude, self.customer_longitude,
                float(pharmacy.latitude), float(pharmacy.longitude),
            )
            if distance <= 10:
                pharmacy.distance_km = round(distance, 2)
                nearby.append(pharmacy)
        return sorted(nearby, key=lambda pharmacy: pharmacy.distance_km)


def _coords(value):
    """Parse a lat/lng query-param string as a float, or None."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _valid_coords(latitude, longitude):
    """True when both coords are present and inside valid geospatial ranges."""
    if latitude is None or longitude is None:
        return False
    return -90 <= latitude <= 90 and -180 <= longitude <= 180


class HomePharmaciesView(generics.ListAPIView):
    """GET /pharmacy/home/  — the customer home-page section.

    Returns every verified & open pharmacy sorted nearest-first:
      * if `latitude` (+`longitude`) query params are supplied, they win;
      * otherwise the authenticated customer's default-address coords are used;
      * if no location is available, falls back to alphabetical by business name.

    Every row carries `distance_km` so the mobile/home UI can show distance.
    `location_source` tells the client which coords were used for the sort.
    """

    serializer_class = NearbyPharmacySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    pagination_class = None

    def list(self, request, *args, **kwargs):
        latitude = _coords(request.query_params.get("latitude") or request.query_params.get("lat"))
        longitude = _coords(request.query_params.get("longitude") or request.query_params.get("lng"))
        source = "query"

        if not _valid_coords(latitude, longitude):
            latitude, longitude = None, None
            lat, lng, source = self._location_from_request(request)
            if lat is not None:
                latitude, longitude = lat, lng

        pharmacies = list(
            PharmacyProfile.objects.filter(is_verified=True, is_open=True)
            .order_by("business_name")
        )

        for pharmacy in pharmacies:
            if latitude is not None and longitude is not None and pharmacy.latitude is not None and pharmacy.longitude is not None:
                pharmacy.distance_km = round(_distance_km(
                    latitude, longitude,
                    float(pharmacy.latitude), float(pharmacy.longitude),
                ), 2)
            else:
                pharmacy.distance_km = None

        if latitude is not None and longitude is not None:
            pharmacies.sort(key=lambda p: p.distance_km if p.distance_km is not None else float("inf"))
        else:
            pharmacies.sort(key=lambda p: p.business_name.lower())

        serializer = self.get_serializer(pharmacies, many=True)
        data = serializer.data
        payload = {
            "count": len(data),
            "location_source": source,
            "latitude": latitude,
            "longitude": longitude,
            "pharmacies": data,
        }
        return Response(payload)

    def _location_from_request(self, request):
        """Fall back to the authenticated customer's default-address coordinates."""
        user = request.user
        if user is None or not user.is_authenticated:
            return None, None, "none"
        if user.role != "customer":
            return None, None, "none"
        from apps.customer.models import CustomerProfile, Address

        profile = CustomerProfile.objects.filter(user=user).first()
        if not profile:
            return None, None, "none"
        address = Address.objects.filter(customer=profile, is_default=True).first()
        if not address:
            address = Address.objects.filter(customer=profile).first()
        if not address or address.latitude is None or address.longitude is None:
            return None, None, "none"
        return float(address.latitude), float(address.longitude), "default_address"


class InventoryViewSet(viewsets.ModelViewSet):
    serializer_class = InventoryItemSerializer
    permission_classes = [IsPharmacy]

    def get_queryset(self):
        if self.request.user.is_superuser or self.request.user.role == "admin":
            return InventoryItem.objects.all()
        return InventoryItem.objects.filter(pharmacy__user=self.request.user)

    def perform_create(self, serializer):
        from django.db import IntegrityError
        pharmacy = _pharmacy(self.request)
        medicine = serializer.validated_data.get("medicine")
        if medicine and InventoryItem.objects.filter(pharmacy=pharmacy, medicine=medicine).exists():
            raise ValidationError({"detail": "An inventory row for this medicine already exists at your pharmacy."})
        try:
            serializer.save(pharmacy=pharmacy)
        except IntegrityError:
            raise ValidationError({"detail": "An inventory row for this medicine already exists at your pharmacy."})


class IncomingOrdersView(generics.ListAPIView):
    """Receive and review incoming orders."""

    serializer_class = OrderSerializer
    permission_classes = [IsPharmacy]

    def get_queryset(self):
        queryset = Order.objects.all() if self.request.user.is_superuser or self.request.user.role == "admin" else Order.objects.filter(pharmacy__user=self.request.user)
        return queryset.exclude(
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
        try:
            if action == "reject":
                order.set_status(OrderStatus.CANCELLED, changed_by=request.user, note="Rejected by pharmacy")
            elif action in self.ACTIONS:
                self.ACTIONS[action](order, request.user)
            else:
                return Response({"detail": "Unknown action."}, status=400)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(OrderSerializer(order).data)


class VerifyPrescriptionView(APIView):
    """FR-05 + Pharmacist Copilot: approve/reject an AI-extracted prescription."""

    permission_classes = [IsPharmacy]

    def post(self, request, prescription_id):
        prescription = get_object_or_404(
            Prescription, id=prescription_id, pharmacy=_pharmacy(request)
        )
        if prescription.status not in ("uploaded", "processing", "needs_review"):
            return Response(
                {"detail": f"This prescription is already {prescription.status}."},
                status=400,
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
        queryset = Prescription.objects.all() if self.request.user.is_superuser or self.request.user.role == "admin" else Prescription.objects.filter(pharmacy__user=self.request.user)
        return queryset.order_by("-created_at")

    def list(self, request, *args, **kwargs):
        # Ensure AI-extracted items are parsed into PrescriptionItem rows so
        # the pharmacy app can review the extracted medicine lines (B7/B12).
        for prescription in self.get_queryset():
            from apps.customer.services import parse_ai_extraction_into_items
            parse_ai_extraction_into_items(prescription)
        return super().list(request, *args, **kwargs)


class DemandForecastView(generics.ListAPIView):
    """FR-14: pharmacy dashboard consumes forecasts generated by the AI
    service's scheduled job (G. Inventory Forecasting)."""

    serializer_class = DemandForecastSerializer
    permission_classes = [IsPharmacy]

    def get_queryset(self):
        queryset = DemandForecast.objects.all() if self.request.user.is_superuser or self.request.user.role == "admin" else DemandForecast.objects.filter(pharmacy__user=self.request.user)
        return queryset.order_by("-generated_at")


class GenerateForecastsView(APIView):
    """POST /pharmacy/forecasts/generate/ — rebuild demand forecasts for the
    current pharmacy from its real order history (click "Refresh" on the
    pharmacy dashboard)."""

    permission_classes = [IsPharmacy]

    def post(self, request):
        pharmacy = _pharmacy(request)
        lookback = request.data.get("lookback_days", 30)
        horizon = request.data.get("horizon_days", 7)
        try:
            lookback = int(lookback)
            horizon = int(horizon)
        except (TypeError, ValueError):
            return Response({"detail": "lookback_days and horizon_days must be integers."}, status=400)
        if not (1 <= lookback <= 365) or not (1 <= horizon <= 90):
            return Response({"detail": "lookback_days must be 1-365 and horizon_days 1-90."}, status=400)

        forecasts = services.generate_demand_forecasts(pharmacy, lookback_days=lookback, horizon_days=horizon)
        rows = [
            {"medicine": name, "current_stock": stock, "expected_demand": demand, "recommended_restock": restock}
            for name, stock, demand, restock in forecasts
        ]
        return Response({"count": len(rows), "forecasts": rows})
