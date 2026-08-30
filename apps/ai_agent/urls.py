from django.urls import path

from .views import (
    AIHealthCheckView,
    ChatSessionDetailView,
    ChatSessionListView,
    ChatView,
    ImageMatchView,
    SemanticMedicineSearchView,
)

urlpatterns = [
    # Chat
    path("chat/", ChatView.as_view(), name="ai-chat"),
    path("sessions/", ChatSessionListView.as_view(), name="ai-sessions"),
    path("sessions/<int:pk>/", ChatSessionDetailView.as_view(), name="ai-session-detail"),
    # Standalone search (no chat context)
    path("search/", SemanticMedicineSearchView.as_view(), name="ai-medicine-search"),
    path("image-match/", ImageMatchView.as_view(), name="ai-image-match"),
    # System
    path("health/", AIHealthCheckView.as_view(), name="ai-health"),
]
