from django.utils import timezone

from apps.accounts.models import AuditLog
from apps.orders.models import OrderStatus

from .models import PrescriptionReview


def verify_prescription(prescription, pharmacy, reviewer, decision, notes=""):
    """FR-05: pharmacist verification is the final authority — AI never
    auto-approves (matches slide 'AI does not automatically approve
    prescriptions')."""
    PrescriptionReview.objects.create(
        prescription=prescription, pharmacy=pharmacy, reviewed_by=reviewer, decision=decision, notes=notes
    )
    prescription.status = "verified" if decision == "approved" else "rejected"
    prescription.reviewed_by = reviewer
    prescription.reviewed_at = timezone.now()
    if decision != "approved":
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
