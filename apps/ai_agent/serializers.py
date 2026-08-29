from rest_framework import serializers

from apps.catalog.serializers import MedicineSerializer

from .models import ChatMessage, ChatSession


class ChatSessionSerializer(serializers.ModelSerializer):
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = ChatSession
        fields = ["id", "language", "message_count", "created_at", "updated_at"]
        read_only_fields = fields

    def get_message_count(self, obj):
        return obj.messages.count()


class ChatMessageSerializer(serializers.ModelSerializer):
    matched_medicines = MedicineSerializer(many=True, read_only=True)

    class Meta:
        model = ChatMessage
        fields = [
            "id", "role", "content", "intent", "confidence",
            "detected_language", "entities", "matched_medicines",
            "created_at",
        ]
        read_only_fields = fields


class ChatInputSerializer(serializers.Serializer):
    """Input for the main chat endpoint."""

    message = serializers.CharField(max_length=2000)
    session_id = serializers.IntegerField(required=False, allow_null=True)
    image = serializers.ImageField(required=False, allow_null=True)


class MedicineSearchInputSerializer(serializers.Serializer):
    """Input for the semantic medicine search endpoint."""

    query = serializers.CharField(max_length=500)
    top_k = serializers.IntegerField(default=10, min_value=1, max_value=50)
    min_score = serializers.FloatField(default=0.3, min_value=0.0, max_value=1.0)


class MedicineImageMatchSerializer(serializers.Serializer):
    """Input for the image-based medicine matching endpoint."""

    image = serializers.ImageField()
    top_k = serializers.IntegerField(default=5, min_value=1, max_value=20)


class AIHealthCheckSerializer(serializers.Serializer):
    """Response for the AI system health check."""

    ollama_available = serializers.BooleanField()
    ollama_model = serializers.CharField()
    embeddings_count = serializers.IntegerField()
    intent_classifier_loaded = serializers.BooleanField()
