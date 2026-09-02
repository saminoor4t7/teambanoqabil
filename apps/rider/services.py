from math import asin, cos, radians, sin, sqrt
import random

from django.utils import timezone

from apps.orders.models import Delivery, OrderStatus

from .models import DeliveryOffer, RiderProfile


def _distance_km(latitude_one, longitude_one, latitude_two, longitude_two):
    """Great-circle distance between two GPS points in kilometres."""
    earth_radius_km = 6371
    latitude_delta = radians(float(latitude_two) - float(latitude_one))
    longitude_delta = radians(float(longitude_two) - float(longitude_one))
    value = (
        sin(latitude_delta / 2) ** 2
        + cos(radians(float(latitude_one)))
        * cos(radians(float(latitude_two)))
        * sin(longitude_delta / 2) ** 2
    )
    return earth_radius_km * 2 * asin(sqrt(value))


def _score_rider(rider, distance_km):
    """Stand-in for H. Dispatch/ETA Intelligence (distance, traffic, rider
    location, current orders, rider capacity, time of day). Swap this for
    a call to the AI service's scoring endpoint when it's available."""
    load_penalty = rider.active_delivery_count * 5
    return -(distance_km + load_penalty)


def request_rider_assignment(order):
    """AI Rider Assignment (slide 14): evaluates eligible riders and
    assigns the best-scoring one, mirroring 'AI -> Rider B' in the deck."""
    delivery, _ = Delivery.objects.get_or_create(order=order)

    pharmacy = order.pharmacy
    candidates = RiderProfile.objects.filter(
        is_available=True,
        is_verified=True,
        vehicle_type__gt="",
        vehicle_number__gt="",
        address_line__gt="",
        city__gt="",
        current_latitude__isnull=False,
        current_longitude__isnull=False,
    )

    # Score each rider exactly once so the stored offer score matches the
    # ranking decision (B14) and dispatch is deterministic for a given ETA.
    scored = []
    if pharmacy.latitude is not None and pharmacy.longitude is not None:
        for rider in candidates:
            distance_km = _distance_km(
                rider.current_latitude, rider.current_longitude,
                pharmacy.latitude, pharmacy.longitude,
            )
            scored.append((rider, distance_km, _score_rider(rider, distance_km)))
    scored.sort(key=lambda item: item[1])

    # Invalidate any previously outstanding offers on this delivery.
    delivery.offers.filter(status="offered").update(status="expired")

    for rider, distance_km, score in scored[:3]:
        DeliveryOffer.objects.create(
            delivery=delivery,
            rider=rider,
            distance_km=round(distance_km, 2),
            score=round(score, 4),
        )
    return delivery


def assign_rider(delivery, rider):
    delivery.rider = rider
    delivery.assigned_at = timezone.now()
    delivery.eta_minutes_min, delivery.eta_minutes_max = predict_eta(delivery)
    delivery.save(update_fields=["rider", "assigned_at", "eta_minutes_min", "eta_minutes_max"])
    # Once a rider is chosen, expire all other open offers on this delivery
    # so losing riders don't see stale "offered" requests (B14).
    delivery.offers.exclude(rider=rider).filter(status="offered").update(status="expired")
    return delivery


def predict_eta(delivery):
    """ETA Prediction (slide 14): historical delivery times, traffic,
    distance, pharmacy prep time, rider behaviour, time of day. Simple
    heuristic placeholder — replace with the AI service call."""
    base = random.randint(12, 18)
    return base - 2, base + 2


def confirm_pickup(delivery, rider_user):
    delivery.picked_up_at = timezone.now()
    delivery.save(update_fields=["picked_up_at"])
    delivery.order.set_status(OrderStatus.PICKED_UP, changed_by=rider_user)
    return delivery


def start_delivery(delivery, rider_user):
    delivery.order.set_status(OrderStatus.ON_THE_WAY, changed_by=rider_user)
    return delivery


def confirm_delivered(delivery, rider_user):
    delivery.delivered_at = timezone.now()
    delivery.save(update_fields=["delivered_at"])
    delivery.order.set_status(OrderStatus.DELIVERED, changed_by=rider_user)
    delivery.order.is_paid = True if delivery.order.payment_method == "cod" else delivery.order.is_paid
    delivery.order.save(update_fields=["is_paid"])
    return delivery
