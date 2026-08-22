from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    DemandForecastView,
    IncomingOrdersView,
    InventoryViewSet,
    MyPharmacyView,
    OrderTransitionView,
    VerifyPrescriptionView,
)

router = DefaultRouter()
router.register("inventory", InventoryViewSet, basename="inventory")

urlpatterns = [
    path("me/", MyPharmacyView.as_view(), name="pharmacy-me"),
    path("orders/incoming/", IncomingOrdersView.as_view(), name="incoming-orders"),
    path("orders/<int:order_id>/<str:action>/", OrderTransitionView.as_view(), name="order-transition"),
    path("prescriptions/<int:prescription_id>/verify/", VerifyPrescriptionView.as_view(), name="verify-prescription"),
    path("forecasts/", DemandForecastView.as_view(), name="demand-forecasts"),
] + router.urls
