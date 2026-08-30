"""
AI Agent API views.

Endpoints:
  POST /ai/chat/               — main conversational agent
  GET  /ai/sessions/           — list user's chat sessions
  GET  /ai/sessions/<id>/      — session detail + messages
  DELETE /ai/sessions/<id>/   — delete a session
  POST /ai/search/             — semantic medicine search (no chat)
  POST /ai/image-match/        — match a medicine photo (no chat)
  GET  /ai/health/             — AI system health check
"""

import logging

from rest_framework import generics, parsers, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.customer.permissions import IsCustomer

from .models import ChatMessage, ChatSession, MedicineEmbedding
from .serializers import (
    AIHealthCheckSerializer,
    ChatInputSerializer,
    ChatMessageSerializer,
    ChatSessionSerializer,
    MedicineImageMatchSerializer,
    MedicineSearchInputSerializer,
)

logger = logging.getLogger(__name__)


# ── Chat endpoints ────────────────────────────────────────────────────


class ChatView(APIView):
    """Main AI agent endpoint: accepts text (and optional image),
    returns intent + matched medicines + conversational response."""

    permission_classes = [permissions.IsAuthenticated, IsCustomer]
    parser_classes = [parsers.MultiPartParser, parsers.JSONParser]

    def post(self, request):
        serializer = ChatInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Get or create session
        customer = request.user.customer_profile
        session_id = data.get("session_id")

        if session_id:
            try:
                session = ChatSession.objects.get(id=session_id, customer=customer)
            except ChatSession.DoesNotExist:
                return Response(
                    {"detail": "Chat session not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            session = ChatSession.objects.create(customer=customer)

        # Read image bytes if uploaded
        image_data = None
        image_file = data.get("image")
        if image_file:
            image_data = image_file.read()

        # Process through the AI agent pipeline
        from .services import response_generator
        result = response_generator.handle_message(
            session=session,
            user_text=data["message"],
            image_data=image_data,
        )

        return Response({
            "session_id": session.id,
            **result,
        })


class ChatSessionListView(generics.ListAPIView):
    """List all chat sessions for the current customer."""

    serializer_class = ChatSessionSerializer
    permission_classes = [permissions.IsAuthenticated, IsCustomer]

    def get_queryset(self):
        return ChatSession.objects.filter(
            customer=self.request.user.customer_profile
        )


class ChatSessionDetailView(generics.RetrieveDestroyAPIView):
    """Retrieve or delete a chat session (includes all messages)."""

    serializer_class = ChatSessionSerializer
    permission_classes = [permissions.IsAuthenticated, IsCustomer]

    def get_queryset(self):
        return ChatSession.objects.filter(
            customer=self.request.user.customer_profile
        )

    def retrieve(self, request, *args, **kwargs):
        session = self.get_object()
        messages = session.messages.all()[:50]  # last 50 messages
        session_data = ChatSessionSerializer(session).data
        messages_data = ChatMessageSerializer(messages, many=True).data
        return Response({
            **session_data,
            "messages": messages_data,
        })


# ── Standalone search endpoints (no chat context needed) ─────────────


class SemanticMedicineSearchView(APIView):
    """Semantic search over the medicine catalog using sentence-transformers.

    Does NOT create a chat session — use this for autocomplete or
    search-box functionality.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = MedicineSearchInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        from .services import medicine_matcher
        results = medicine_matcher.search(
            query=data["query"],
            top_k=data["top_k"],
            min_score=data["min_score"],
        )

        from apps.catalog.serializers import MedicineSerializer

        return Response({
            "query": data["query"],
            "count": len(results),
            "results": [
                {
                    **MedicineSerializer(r["medicine"]).data,
                    "match_score": r["score"],
                }
                for r in results
            ],
        })


class ImageMatchView(APIView):
    """Upload a medicine photo and find matching catalog entries."""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser]

    def post(self, request):
        serializer = MedicineImageMatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        image_data = data["image"].read()
        from .services import image_analyzer

        matches = image_analyzer.match_image(
            image_data,
            top_k=data["top_k"],
            min_score=0.4,
        )

        from apps.catalog.serializers import MedicineSerializer

        return Response({
            "count": len(matches),
            "results": [
                {
                    **MedicineSerializer(m["medicine"]).data,
                    "match_score": m["score"],
                }
                for m in matches
            ],
        })


# ── System health ─────────────────────────────────────────────────────


class AIHealthCheckView(APIView):
    """Check the health of all AI subsystems."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from .services import nlp_engine, ollama_client
        classifier = nlp_engine.get_classifier()
        data = {
            "ollama_available": ollama_client.is_available(),
            "ollama_model": ollama_client.OLLAMA_MODEL,
            "embeddings_count": MedicineEmbedding.objects.count(),
            "intent_classifier_loaded": classifier.pipeline is not None,
        }
        return Response(data)
