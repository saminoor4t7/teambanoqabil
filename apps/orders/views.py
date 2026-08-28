from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Order, Refund
from .serializers import OrderSerializer, RefundSerializer


class MyOrdersView(generics.ListAPIView):
    """Role-aware order history: a customer sees their own orders, a
    pharmacy sees orders placed with them, a rider sees deliveries
    assigned to them — one endpoint reused by all three apps."""

    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == "customer":
            return Order.objects.filter(customer__user=user)
        if user.role == "pharmacy":
            return Order.objects.filter(pharmacy__user=user)
        if user.role == "rider":
            return Order.objects.filter(delivery__rider__user=user)
        if user.is_superuser or user.role == "admin":
            return Order.objects.all()
        return Order.objects.none()


class OrderDetailView(generics.RetrieveAPIView):
    """Live order tracking — used by the customer app's 'track order'
    screen and the support panel's 'live order support' tool."""

    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Order.objects.all()

    def get_queryset(self):
        user = self.request.user
        qs = Order.objects.all()
        if user.role == "customer":
            return qs.filter(customer__user=user)
        if user.role == "pharmacy":
            return qs.filter(pharmacy__user=user)
        if user.role == "rider":
            return qs.filter(delivery__rider__user=user)
        if user.role in ("support", "admin"):
            return qs
        return qs.none()


class RequestRefundView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, order_id):
        order_filter = {"id": order_id}
        if not (request.user.is_superuser or request.user.role == "admin"):
            order_filter["customer__user"] = request.user
        order = get_object_or_404(Order, **order_filter)
        serializer = RefundSerializer(data={**request.data, "order": order.id})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=201)
