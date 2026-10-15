import logging
import re
from difflib import SequenceMatcher

from django.db.models import Q
from rest_framework import generics, parsers, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.medical_store.models import InventoryItem, PharmacyProfile
from apps.customer.permissions import IsCustomer

from .models import Brand, Category, Medicine
from .serializers import (
    BrandSerializer,
    CategorySerializer,
    MedicineAvailabilityScanSerializer,
    MedicineSerializer,
)

logger = logging.getLogger(__name__)


class IsAdminOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS or (
            request.user.is_authenticated and (request.user.is_superuser or request.user.role == "admin")
        )


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.order_by("name", "pk")
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]


class BrandViewSet(viewsets.ModelViewSet):
    queryset = Brand.objects.all()
    serializer_class = BrandSerializer
    permission_classes = [IsAdminOrReadOnly]


class MedicineViewSet(viewsets.ModelViewSet):
    """FR-07: natural-language / name / category search surfaces here.
    The AI assistant calls this same endpoint after resolving intent —
    it never invents medicines outside this queryset."""

    queryset = Medicine.objects.filter(is_active=True).order_by("name", "pk")
    serializer_class = MedicineSerializer
    permission_classes = [IsAdminOrReadOnly]
    filterset_fields = ["category", "brand", "requires_prescription"]
    search_fields = ["name", "generic_name"]

    def get_queryset(self):
        qs = super().get_queryset()
        pharmacy_id = self.request.query_params.get("pharmacy_id")
        if pharmacy_id:
            # The customer storefront is scoped to the selected pharmacy.
            # A medicine belongs in that storefront only after the pharmacy
            # has added it to its inventory.
            qs = qs.filter(
                inventory_items__pharmacy_id=pharmacy_id,
                inventory_items__pharmacy__is_verified=True,
                inventory_items__pharmacy__is_open=True,
            ).distinct()
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(generic_name__icontains=q)
                | Q(category__name__icontains=q)
            ).distinct()
        return qs



class MedicineSearchView(generics.ListAPIView):
    serializer_class = MedicineSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        query = self.request.query_params.get("q", "").strip()
        if not query:
            return Medicine.objects.none()
        return Medicine.objects.filter(is_active=True).filter(
            Q(name__icontains=query)
            | Q(generic_name__icontains=query)
            | Q(category__name__icontains=query)
        ).distinct().order_by("name", "pk")


def _normalise_ocr_text(value):
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _medicine_text_score(ocr_text, medicine):
    text = _normalise_ocr_text(ocr_text)
    ocr_words = text.split()
    aliases = [medicine.name, medicine.generic_name]
    if medicine.brand_id:
        aliases.append(medicine.brand.name)

    best = 0.0
    for alias in aliases:
        alias = _normalise_ocr_text(alias or "")
        if not alias:
            continue
        if re.search(rf"\b{re.escape(alias)}\b", text):
            return 1.0
        alias_words = alias.split()
        if len(alias_words) == 1:
            score = max((SequenceMatcher(None, alias, word).ratio() for word in ocr_words), default=0)
            best = max(best, score * 0.9)
        else:
            word_scores = [
                max((SequenceMatcher(None, word, found).ratio() for found in ocr_words), default=0)
                for word in alias_words
            ]
            coverage = sum(score >= 0.78 for score in word_scores) / len(word_scores)
            best = max(best, sum(word_scores) / len(word_scores) * coverage)
    return best


class MedicineAvailabilityScanView(APIView):
    """Match OCR text (or text read from a photo) and check one pharmacy's stock."""

    permission_classes = [permissions.IsAuthenticated, IsCustomer]
    parser_classes = [parsers.JSONParser, parsers.MultiPartParser, parsers.FormParser]

    def post(self, request):
        serializer = MedicineAvailabilityScanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        pharmacy = PharmacyProfile.objects.filter(
            pk=data["pharmacy_id"], is_verified=True, is_open=True
        ).first()
        if pharmacy is None:
            return Response(
                {"detail": "Selected pharmacy is not available."},
                status=status.HTTP_404_NOT_FOUND,
            )

        ocr_text = data["text"]
        if not ocr_text:
            try:
                import pytesseract
            except ImportError:
                return Response(
                    {"detail": "Python OCR support is missing. Install requirements.txt, then restart Django."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            try:
                from django.conf import settings
                from PIL import Image, ImageOps

                if getattr(settings, "TESSERACT_CMD", ""):
                    pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
                with Image.open(data["image"]) as source:
                    image = ImageOps.grayscale(source)
                    image = ImageOps.autocontrast(image)
                    longest_side = max(image.size)
                    if longest_side < 1400:
                        scale = min(2, 1400 / longest_side)
                        image = image.resize((int(image.width * scale), int(image.height * scale)))
                    elif longest_side > 1800:
                        scale = 1800 / longest_side
                        image = image.resize((int(image.width * scale), int(image.height * scale)))
                    ocr_text = pytesseract.image_to_string(image, config="--psm 6", timeout=15).strip()
            except pytesseract.TesseractNotFoundError:
                return Response(
                    {"detail": "Tesseract OCR engine is not installed. Install it and set TESSERACT_CMD if needed, then restart Django."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            except RuntimeError:
                return Response(
                    {"detail": "OCR took too long. Try a clearer or smaller image."},
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            except Exception as exc:
                logger.warning("Medicine image OCR failed: %s", exc, exc_info=True)
                return Response(
                    {"detail": "Could not read text from this image. Try a clear, upright photo of the package."},
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )

        if not ocr_text:
            return Response({"recognized_text": "", "matched": False, "available": False})

        candidates = [
            (_medicine_text_score(ocr_text, medicine), medicine)
            for medicine in Medicine.objects.filter(is_active=True).select_related("brand")
        ]
        score, medicine = max(candidates, key=lambda item: item[0], default=(0, None))
        if medicine is None or score < 0.72:
            return Response({
                "recognized_text": ocr_text,
                "matched": False,
                "available": False,
                "medicine": None,
                "stock": 0,
            })

        inventory = InventoryItem.objects.filter(pharmacy=pharmacy, medicine=medicine).first()
        stock = inventory.quantity_in_stock if inventory else 0
        return Response({
            "recognized_text": ocr_text,
            "matched": True,
            "available": stock > 0,
            "match_score": round(score, 3),
            "medicine": {
                "id": medicine.id,
                "name": medicine.name,
                "generic_name": medicine.generic_name,
                "strength": medicine.strength,
            },
            "stock": stock,
            "pharmacy": pharmacy.business_name,
        })
