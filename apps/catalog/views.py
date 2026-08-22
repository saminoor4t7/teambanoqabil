from rest_framework import permissions, viewsets

from .models import Brand, Category, Medicine
from .serializers import BrandSerializer, CategorySerializer, MedicineSerializer


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class BrandViewSet(viewsets.ModelViewSet):
    queryset = Brand.objects.all()
    serializer_class = BrandSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class MedicineViewSet(viewsets.ModelViewSet):
    """FR-07: natural-language / name / category search surfaces here.
    The AI assistant calls this same endpoint after resolving intent —
    it never invents medicines outside this queryset."""

    queryset = Medicine.objects.filter(is_active=True)
    serializer_class = MedicineSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filterset_fields = ["category", "brand", "requires_prescription"]
    search_fields = ["name", "generic_name"]

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        if q:
            from django.db.models import Q
            qs = qs.filter(Q(name__icontains=q) | Q(generic_name__icontains=q))
        return qs
