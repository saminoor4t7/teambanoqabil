from django.urls import path

from .views import AIChatView, AIConversationDetailView, AIConversationListView

urlpatterns = [
    path("chat/", AIChatView.as_view(), name="ai-chat"),
    path("conversations/", AIConversationListView.as_view(), name="ai-conversations"),
    path("conversations/<int:pk>/", AIConversationDetailView.as_view(), name="ai-conversation-detail"),
]
