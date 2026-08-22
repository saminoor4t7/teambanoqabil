import random

from django.utils import timezone

from apps.orders.models import Delivery, OrderStatus

from .models import DeliveryOffer, RiderProfile


def _score_rider(rider):
    """Stand-in for H. Dispatch/ETA Intelligence (distance, traffic, rider
    location, current orders, rider capacity, time of day). Swap this for
    a call to the AI service's scoring endpoint when it's available."""
    load_penalty = rider.active_delivery_count * 5
    return random.uniform(0, 10) - load_penalty


def request_rider_assignment(order):
    """AI Rider Assignment (slide 14): evaluates eligible riders and
    assigns the best-scoring one, mirroring 'AI -> Rider B' in the deck."""
    delivery, _ = Delivery.objects.get_or_create(order=order)

    candidates = RiderProfile.objects.filter(is_available=True, is_verified=True)
    scored = sorted(candidates, key=_score_rider, reverse=True)

    for rider in scored[:3]:
        DeliveryOffer.objects.create(delivery=delivery, rider=rider, score=_score_rider(rider))

    if scored:
        best = scored[0]
        assign_rider(delivery, best)
    return delivery


def assign_rider(delivery, rider):
    delivery.rider = rider
    delivery.assigned_at = timezone.now()
    delivery.eta_minutes_min, delivery.eta_minutes_max = predict_eta(delivery)
    delivery.save(update_fields=["rider", "assigned_at", "eta_minutes_min", "eta_minutes_max"])
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
