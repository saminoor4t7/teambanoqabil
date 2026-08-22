from rest_framework.routers import DefaultRouter

from .views import BrandViewSet, CategoryViewSet, MedicineViewSet

router = DefaultRouter()
router.register("medicines", MedicineViewSet, basename="medicine")
router.register("categories", CategoryViewSet, basename="category")
router.register("brands", BrandViewSet, basename="brand")

urlpatterns = router.urls
