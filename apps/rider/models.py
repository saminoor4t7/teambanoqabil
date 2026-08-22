from django.conf import settings
from django.db import models


class RiderProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rider_profile")
    vehicle_type = models.CharField(max_length=30, blank=True)
    cnic_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    is_available = models.BooleanField(default=True)  # toggled online/offline by the rider
    current_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    current_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def active_delivery_count(self):
        return self.deliveries.exclude(order__status__in=["delivered", "cancelled"]).count()

    def __str__(self):
        return f"Rider: {self.user.username}"


class RiderLocationPing(models.Model):
    """Live location trail, feeding both customer tracking and the H.
    Dispatch/ETA Intelligence signal set (distance, rider location)."""

    rider = models.ForeignKey(RiderProfile, on_delete=models.CASCADE, related_name="location_pings")
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]


class DeliveryOffer(models.Model):
    """A dispatch offer sent to one or more candidate riders for a given
    Delivery — lets multiple riders be scored/offered without directly
    coupling the rider app to pharmacy-side order logic."""

    delivery = models.ForeignKey("orders.Delivery", on_delete=models.CASCADE, related_name="offers")
    rider = models.ForeignKey(RiderProfile, on_delete=models.CASCADE, related_name="offers")
    distance_km = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    score = models.FloatField(null=True, blank=True)
    status = models.CharField(
        max_length=15,
        choices=[("offered", "Offered"), ("accepted", "Accepted"), ("declined", "Declined"), ("expired", "Expired")],
        default="offered",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-score", "distance_km"]
