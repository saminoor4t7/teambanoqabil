"""
Management command: build medicine embeddings for the AI agent.

Usage:
    python manage.py ai_build_embeddings
    python manage.py ai_build_embeddings --force        # rebuild all
    python manage.py ai_build_embeddings --images       # also build image embeddings
"""

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Build sentence-transformer embeddings for all catalog medicines."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-encode all medicines even if their text hasn't changed.",
        )
        parser.add_argument(
            "--images",
            action="store_true",
            help="Also compute image embeddings for medicines with photos.",
        )

    def handle(self, *args, **options):
        from apps.ai_agent.services import image_analyzer, medicine_matcher
        from apps.ai_agent.models import MedicineEmbedding
        from apps.catalog.models import Medicine

        # ── Text embeddings ───────────────────────────────────────────
        self.stdout.write("Building text embeddings...")
        count = medicine_matcher.build_embeddings(force=options["force"])
        self.stdout.write(self.style.SUCCESS(f"  Created/updated {count} text embeddings."))

        # ── Image embeddings (optional) ───────────────────────────────
        if options["images"]:
            self.stdout.write("Building image embeddings...")
            medicines_with_images = Medicine.objects.filter(
                is_active=True,
                image__isnull=False,
            ).exclude(image="")

            img_count = 0
            for med in medicines_with_images:
                try:
                    med.image.open("rb")
                    img_bytes = med.image.read()
                    med.image.close()

                    vec = image_analyzer.build_medicine_image_embedding(img_bytes)
                    embedding, _ = MedicineEmbedding.objects.get_or_create(
                        medicine=med,
                        defaults={
                            "vector": [],  # will be filled by text build
                            "model_name": medicine_matcher.MODEL_NAME,
                        },
                    )
                    embedding.image_embedding = vec
                    embedding.save(update_fields=["image_embedding", "updated_at"])
                    img_count += 1
                except Exception as exc:
                    logger.warning("Failed to build image embedding for %s: %s", med.name, exc)

            self.stdout.write(self.style.SUCCESS(f"  Created/updated {img_count} image embeddings."))

        total = MedicineEmbedding.objects.count()
        self.stdout.write(self.style.SUCCESS(f"Total embeddings in DB: {total}"))
