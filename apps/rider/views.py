from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.models import Delivery
from apps.orders.serializers import DeliverySerializer

from . import services
from .models import DeliveryOffer, RiderProfile
from .permissions import IsRider
from .serializers import DeliveryOfferSerializer, RiderLocationPingSerializer, RiderProfileSerializer


def _rider(request):
    return get_object_or_404(RiderProfile, user=request.user)


class MyRiderProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = RiderProfileSerializer
    permission_classes = [IsRider]

    def get_object(self):
        profile, _ = RiderProfile.objects.get_or_create(user=self.request.user)
        return profile


class MyAssignedDeliveriesView(generics.ListAPIView):
    """Login and view today's assigned deliveries."""

    serializer_class = DeliverySerializer
    permission_classes = [IsRider]

    def get_queryset(self):
        queryset = Delivery.objects.all() if self.request.user.is_superuser or self.request.user.role == "admin" else Delivery.objects.filter(rider__user=self.request.user)
        return queryset.exclude(
            order__status__in=["delivered", "cancelled"]
        )


class MyOffersView(generics.ListAPIView):
    """Accept delivery requests in real time — riders poll (or receive via
    push) their pending offers here."""

    serializer_class = DeliveryOfferSerializer
    permission_classes = [IsRider]

    def get_queryset(self):
        if self.request.user.is_superuser or self.request.user.role == "admin":
            return DeliveryOffer.objects.filter(status="offered")
        return DeliveryOffer.objects.filter(rider__user=self.request.user, status="offered")


class RespondToOfferView(APIView):
    permission_classes = [IsRider]

    def post(self, request, offer_id):
        offer = get_object_or_404(DeliveryOffer, id=offer_id, rider__user=request.user)
        decision = request.data.get("decision")  # accepted | declined
        if decision not in ("accepted", "declined"):
            return Response({"detail": "decision must be accepted/declined"}, status=400)
        offer.status = decision
        offer.save(update_fields=["status"])
        if decision == "accepted":
            services.assign_rider(offer.delivery, offer.rider)
        return Response(DeliveryOfferSerializer(offer).data)


class UpdateLocationView(APIView):
    permission_classes = [IsRider]

    def post(self, request):
        rider = _rider(request)
        serializer = RiderLocationPingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(rider=rider)
        rider.current_latitude = serializer.validated_data["latitude"]
        rider.current_longitude = serializer.validated_data["longitude"]
        rider.save(update_fields=["current_latitude", "current_longitude"])
        return Response(serializer.data, status=201)


class DeliveryTransitionView(APIView):
    """POST /api/rider/deliveries/<order_id>/<action>/ where action in
    confirm-pickup|start|confirm-delivered."""

    permission_classes = [IsRider]

    ACTIONS = {
        "confirm-pickup": services.confirm_pickup,
        "start": services.start_delivery,
        "confirm-delivered": services.confirm_delivered,
    }

    def post(self, request, order_id, action):
        delivery = get_object_or_404(Delivery, order_id=order_id, rider__user=request.user)
        if action not in self.ACTIONS:
            return Response({"detail": "Unknown action."}, status=400)
        try:
            delivery = self.ACTIONS[action](delivery, request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(DeliverySerializer(delivery).data)
