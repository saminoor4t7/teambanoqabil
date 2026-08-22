from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path("admin/", admin.site.urls),
    # Auth
    path("auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("accounts/", include("apps.accounts.urls")),
    # Shared reference data (medicines/categories/brands)
    path("catalog/", include("apps.catalog.urls")),
    # The three interconnected role apps
    path("customer/", include("apps.customer.urls")),
    path("pharmacy/", include("apps.medical_store.urls")),
    path("rider/", include("apps.rider.urls")),
    # Interconnection hub: orders + delivery lifecycle
    path("orders/", include("apps.orders.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
