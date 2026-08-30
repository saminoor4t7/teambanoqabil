from django.db import models


class ChatSession(models.Model):
    """A conversation thread between a customer and the AI agent."""

    LANGUAGE_CHOICES = [
        ("en", "English"),
        ("roman_ur", "Roman Urdu"),
        ("mixed", "Mixed"),
    ]

    customer = models.ForeignKey(
        "customer.CustomerProfile",
        on_delete=models.CASCADE,
        related_name="ai_chat_sessions",
    )
    language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES, default="en")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Chat #{self.id} — {self.customer} ({self.language})"


class ChatMessage(models.Model):
    """One message in a chat session — user or agent."""

    ROLE_CHOICES = [
        ("user", "User"),
        ("agent", "Agent"),
        ("system", "System"),
    ]

    INTENT_CHOICES = [
        ("medicine_search", "Medicine Search"),
        ("category_browse", "Browse Category"),
        ("medicine_info", "Medicine Information"),
        ("image_match", "Image Match"),
        ("order_status", "Order Status"),
        ("general", "General Conversation"),
        ("unknown", "Unknown"),
    ]

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    intent = models.CharField(max_length=30, choices=INTENT_CHOICES, blank=True)
    detected_language = models.CharField(max_length=10, blank=True)
    entities = models.JSONField(default=dict, blank=True)  # extracted entities
    matched_medicines = models.ManyToManyField(
        "catalog.Medicine", blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.role}] {self.content[:60]}"


class MedicineEmbedding(models.Model):
    """Pre-computed sentence-transformer embedding for each catalog medicine.

    Stored as a JSON array of floats so we can do cosine similarity in Python
    without a separate vector database — the catalog is small enough (< 10k
    medicines) that a brute-force numpy scan is fast enough."""

    medicine = models.OneToOneField(
        "catalog.Medicine",
        on_delete=models.CASCADE,
        related_name="embedding",
    )
    # Serialised numpy vector — keeps the schema simple and portable.
    vector = models.JSONField(help_text="JSON-encoded float32 embedding vector")
    model_name = models.CharField(max_length=100, default="paraphrase-multilingual-MiniLM-L12-v2")
    text_fingerprint = models.CharField(
        max_length=64, blank=True,
        help_text="SHA-256 of the source text; lets us skip re-encoding unchanged rows.",
    )
    image_embedding = models.JSONField(
        null=True, blank=True,
        help_text="JSON-encoded float32 image-feature vector (colour histogram + pHash).",
    )
    updated_at = models.DateTimeField(auto_now=True)

    def get_vector(self):
        import numpy as np
        return np.array(self.vector, dtype=np.float32)

    def get_image_embedding(self):
        if self.image_embedding is None:
            return None
        import numpy as np
        return np.array(self.image_embedding, dtype=np.float32)

    def __str__(self):
        return f"Embedding({self.medicine})"
