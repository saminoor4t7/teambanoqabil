from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.customer.models import CustomerProfile

from .models import Conversation
from .serializers import (
    ChatRequestSerializer,
    ConversationListSerializer,
    ConversationSerializer,
)
from .services import chat_with_ai


def _customer(request):
    return get_object_or_404(CustomerProfile, user=request.user)


class AIChatView(APIView):
    """Main chat endpoint — send a message, get an AI response with optional actions."""

    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        customer = _customer(request)
        conv_id = serializer.validated_data.get("conversation_id")

        if conv_id:
            conversation = get_object_or_404(Conversation, id=conv_id, customer=customer)
        else:
            conversation = Conversation.objects.create(customer=customer)

        result = chat_with_ai(
            customer=customer,
            conversation=conversation,
            user_message=serializer.validated_data["message"],
        )

        return Response(result, status=status.HTTP_200_OK)


class AIConversationListView(generics.ListAPIView):
    """List all conversations for the current customer."""

    serializer_class = ConversationListSerializer

    def get_queryset(self):
        customer = _customer(self.request)
        return Conversation.objects.filter(customer=customer)


class AIConversationDetailView(generics.RetrieveDestroyAPIView):
    """Get full conversation with messages, or delete it."""

    serializer_class = ConversationSerializer

    def get_queryset(self):
        customer = _customer(self.request)
        return Conversation.objects.filter(customer=customer)
