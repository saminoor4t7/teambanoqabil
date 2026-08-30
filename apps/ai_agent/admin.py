from django.contrib import admin

# AI Agent admin registration — chat sessions and embeddings can be
# inspected here for debugging agent behaviour.

from .models import ChatMessage, ChatSession, MedicineEmbedding


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "language", "created_at", "updated_at")
    list_filter = ("language", "created_at")
    search_fields = ("customer__user__username",)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "role", "intent", "created_at")
    list_filter = ("role", "intent")
    search_fields = ("content",)


@admin.register(MedicineEmbedding)
class MedicineEmbeddingAdmin(admin.ModelAdmin):
    list_display = ("medicine", "model_name", "updated_at")
    list_filter = ("model_name",)
