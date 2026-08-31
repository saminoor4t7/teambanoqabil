from django.db import models


class Conversation(models.Model):
    """One chat session between a customer and the Panda AI assistant."""

    customer = models.ForeignKey(
        "customer.CustomerProfile",
        on_delete=models.CASCADE,
        related_name="ai_conversations",
    )
    title = models.CharField(max_length=200, blank=True, default="New Chat")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.title} ({self.customer})"


class ConversationMessage(models.Model):
    """A single message in a conversation -- user, model, or tool result."""

    ROLE_CHOICES = [
        ("user", "User"),
        ("model", "Model"),
        ("tool", "Tool"),
    ]

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField(blank=True, default="")
    tool_calls = models.JSONField(null=True, blank=True)
    action_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Structured data for frontend action cards (medicine list, cart, order preview, etc.)",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.role}] {self.content[:60]}"
