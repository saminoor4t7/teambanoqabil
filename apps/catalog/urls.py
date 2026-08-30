from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import BrandViewSet, CategoryViewSet, MedicineSearchView, MedicineViewSet

router = DefaultRouter()
router.register("medicines", MedicineViewSet, basename="medicine")
router.register("categories", CategoryViewSet, basename="category")
router.register("brands", BrandViewSet, basename="brand")

urlpatterns = router.urls
urlpatterns += [path("search/", MedicineSearchView.as_view(), name="medicine-search")]
