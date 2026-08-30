"""
Management command: train the intent classifier.

Usage:
    python manage.py ai_train_classifier
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Train (or retrain) the NLP intent classifier on the seed dataset."

    def handle(self, *args, **options):
        from apps.ai_agent.services.nlp_engine import IntentClassifier

        self.stdout.write("Training intent classifier...")
        classifier = IntentClassifier()
        classifier.train()

        # Verify by running a few test predictions
        test_queries = [
            "find paracetamol 500mg",
            "where is my order",
            "ye konsi dawai hai",
            "hello",
            "show me antibiotics",
        ]
        self.stdout.write("\nTest predictions:")
        for q in test_queries:
            intent, conf = classifier.predict(q)
            self.stdout.write(f"  '{q}' → {intent} ({conf:.2f})")

        self.stdout.write(self.style.SUCCESS("\nIntent classifier trained and saved."))
