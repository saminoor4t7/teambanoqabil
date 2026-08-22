from django.urls import path

from .views import (
    DeliveryTransitionView,
    MyAssignedDeliveriesView,
    MyOffersView,
    MyRiderProfileView,
    RespondToOfferView,
    UpdateLocationView,
)

urlpatterns = [
    path("me/", MyRiderProfileView.as_view(), name="rider-me"),
    path("deliveries/", MyAssignedDeliveriesView.as_view(), name="rider-deliveries"),
    path("offers/", MyOffersView.as_view(), name="rider-offers"),
    path("offers/<int:offer_id>/respond/", RespondToOfferView.as_view(), name="rider-offer-respond"),
    path("location/", UpdateLocationView.as_view(), name="rider-location"),
    path("deliveries/<int:order_id>/<str:action>/", DeliveryTransitionView.as_view(), name="rider-delivery-transition"),
]
