from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    DemandForecastView,
    GenerateForecastsView,
    HomePharmaciesView,
    IncomingOrdersView,
    IncomingPrescriptionsView,
    InventoryViewSet,
    MyPharmacyView,
    NearbyPharmacyView,
    OrderTransitionView,
    PharmacyDetailView,
    PharmacyDirectoryView,
    PharmacyListView,
    CustomerInventoryView,

    VerifyPrescriptionView,
)

router = DefaultRouter()
router.register("inventory", InventoryViewSet, basename="inventory")

urlpatterns = [
    path("me/", MyPharmacyView.as_view(), name="pharmacy-me"),
    path("list/", PharmacyListView.as_view(), name="pharmacy-list"),
    path("directory/", PharmacyDirectoryView.as_view(), name="pharmacy-directory"),
    path("home/", HomePharmaciesView.as_view(), name="home-pharmacies"),
    path("nearby/", NearbyPharmacyView.as_view(), name="nearby-pharmacies"),
    path("<int:pharmacy_id>/inventory/", CustomerInventoryView.as_view(), name="customer-pharmacy-inventory"),
    path("<int:pharmacy_id>/", PharmacyDetailView.as_view(), name="pharmacy-detail"),

    path("orders/incoming/", IncomingOrdersView.as_view(), name="incoming-orders"),
    path("prescriptions/incoming/", IncomingPrescriptionsView.as_view(), name="incoming-prescriptions"),
    path("orders/<int:order_id>/<str:action>/", OrderTransitionView.as_view(), name="order-transition"),
    path("prescriptions/<int:prescription_id>/verify/", VerifyPrescriptionView.as_view(), name="verify-prescription"),
    path("forecasts/", DemandForecastView.as_view(), name="demand-forecasts"),
    path("forecasts/generate/", GenerateForecastsView.as_view(), name="generate-demand-forecasts"),
] + router.urls
