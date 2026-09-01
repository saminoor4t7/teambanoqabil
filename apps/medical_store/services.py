from collections import defaultdict
from datetime import timedelta

from django.utils import timezone

from apps.accounts.models import AuditLog
from apps.orders.models import OrderStatus

from .models import DemandForecast, PrescriptionReview


def generate_demand_forecasts(pharmacy, lookback_days=30, horizon_days=7):
    """Predict per-medicine demand from real order history (FR-14).

    Uses a simple, explainable daily-sales model: average units sold per
    active sale day, scaled to the forecast horizon. Recommends a restock
    quantity only when expected demand exceeds current stock.

    Idempotent: rebuilds this pharmacy's DemandForecast rows from scratch
    so `generated_at` always reflects the latest run.
    """
    from apps.orders.models import OrderItem

    from .models import InventoryItem

    cutoff = timezone.now() - timedelta(days=lookback_days)

    sales = OrderItem.objects.filter(
        order__pharmacy=pharmacy,
        order__created_at__gte=cutoff,
    ).exclude(order__status=OrderStatus.CANCELLED).values_list(
        "medicine_id", "quantity", "order__created_at"
    )

    quantities = defaultdict(list)
    sale_days = defaultdict(set)
    for medicine_id, quantity, created_at in sales:
        quantities[medicine_id].append(quantity)
        sale_days[medicine_id].add(created_at.date())

    now = timezone.now()
    forecasts = []
    for item in InventoryItem.objects.filter(pharmacy=pharmacy).select_related("medicine"):
        medicine_id = item.medicine_id
        if medicine_id not in quantities:
            continue  # no sales → no forecast churn
        active_days = max(len(sale_days[medicine_id]), 1)
        daily_avg = sum(quantities[medicine_id]) / active_days
        expected_demand = max(0, round(daily_avg * horizon_days))
        current_stock = item.quantity_in_stock
        recommended_restock = max(0, expected_demand - current_stock)

        DemandForecast.objects.update_or_create(
            pharmacy=pharmacy,
            medicine=item.medicine,
            defaults={
                "current_stock": current_stock,
                "expected_demand": expected_demand,
                "recommended_restock": recommended_restock,
                "generated_at": now,
            },
        )
        forecasts.append((item.medicine.name, current_stock, expected_demand, recommended_restock))

    AuditLog.objects.create(
        actor=pharmacy.user,
        action="forecasts_generated",
        target_type="PharmacyProfile",
        target_id=str(pharmacy.id),
        note=f"Forecast rebuilt for {len(forecasts)} medicines ({lookback_days}d history, {horizon_days}d horizon).",
    )
    return forecasts


def verify_prescription(prescription, pharmacy, reviewer, decision, notes=""):
    """FR-05: pharmacist verification is the final authority — AI never
    auto-approves (matches slide 'AI does not automatically approve
    prescriptions')."""
    PrescriptionReview.objects.create(
        prescription=prescription, pharmacy=pharmacy, reviewed_by=reviewer, decision=decision, notes=notes
    )
    if decision == "approved":
        prescription.status = "verified"
    elif decision == "needs_info":
        # Ask-for-more-info keeps it in the review queue for follow-up.
        prescription.status = "needs_review"
        prescription.reviewed_by = reviewer
        prescription.reviewed_at = timezone.now()
        if notes:
            prescription.rejection_reason = notes
        prescription.save()
    else:
        prescription.status = "rejected"
        prescription.reviewed_by = reviewer
        prescription.reviewed_at = timezone.now()
        prescription.rejection_reason = notes
        prescription.save()
    AuditLog.objects.create(
        actor=reviewer, action=f"prescription_{decision}",
        target_type="Prescription", target_id=str(prescription.id),
    )
    return prescription


def accept_order(order, pharmacy_user):
    order.set_status(OrderStatus.ACCEPTED, changed_by=pharmacy_user)
    return order


def mark_preparing(order, pharmacy_user):
    order.set_status(OrderStatus.PREPARING, changed_by=pharmacy_user)
    return order


def mark_ready_for_pickup(order, pharmacy_user):
    """Pack orders and request a nearby rider — this is the hand-off from
    `medical_store` to `rider` via the H. Dispatch/ETA Intelligence flow."""
    order.set_status(OrderStatus.READY_FOR_PICKUP, changed_by=pharmacy_user)
    from apps.rider.services import request_rider_assignment
    request_rider_assignment(order)
    return order
