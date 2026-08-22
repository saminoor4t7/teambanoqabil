from django.urls import path

from .views import MyOrdersView, OrderDetailView, RequestRefundView

urlpatterns = [
    path("", MyOrdersView.as_view(), name="my-orders"),
    path("<int:pk>/", OrderDetailView.as_view(), name="order-detail"),
    path("<int:order_id>/refund/", RequestRefundView.as_view(), name="order-refund"),
]
