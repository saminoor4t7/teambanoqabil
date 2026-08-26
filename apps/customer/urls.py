from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AddressViewSet,
    CartView,
    MyProfileView,
    PlaceOrderView,
    PrescriptionViewSet,
)

router = DefaultRouter()
router.register("addresses", AddressViewSet, basename="address")
router.register("prescriptions", PrescriptionViewSet, basename="prescription")

urlpatterns = [
    path("me/", MyProfileView.as_view(), name="customer-me"),
    path("cart/", CartView.as_view(), name="cart"),
    path("orders/place/", PlaceOrderView.as_view(), name="place-order"),
] + router.urls
