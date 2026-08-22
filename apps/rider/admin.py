from django.contrib import admin

from .models import DeliveryOffer, RiderLocationPing, RiderProfile


@admin.register(RiderProfile)
class RiderProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "vehicle_type", "is_verified", "is_available", "rating"]
    list_filter = ["is_verified", "is_available"]


@admin.register(RiderLocationPing)
class RiderLocationPingAdmin(admin.ModelAdmin):
    list_display = ["rider", "latitude", "longitude", "recorded_at"]


@admin.register(DeliveryOffer)
class DeliveryOfferAdmin(admin.ModelAdmin):
    list_display = ["delivery", "rider", "status", "score", "distance_km", "created_at"]
    list_filter = ["status"]
