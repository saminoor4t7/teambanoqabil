"""
Medicine Matcher — semantic search over the catalog using
sentence-transformers.

Workflow:
  1. `build_embeddings()` — encode every active Medicine into a vector
     and persist in the MedicineEmbedding table. Run via management
     command or after catalog changes.
  2. `search()` — encode the user query and rank all medicine
     vectors by cosine similarity. Returns the top-K matches with
     scores.

Model: paraphrase-multilingual-MiniLM-L12-v2 (120 MB, supports both
English and Roman Urdu reasonably well, 384-dim vectors).
"""

import hashlib
import logging
from functools import lru_cache

import numpy as np

from apps.catalog.models import Medicine

from .language_processor import preprocess

logger = logging.getLogger(__name__)

# Lazy-loaded model — first call downloads ~120 MB, subsequent calls use cache.
_embedder = None
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


def _get_embedder():
    """Lazy-load the sentence-transformer model."""
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(MODEL_NAME)
        logger.info("Loaded sentence-transformer model: %s", MODEL_NAME)
    return _embedder


def _text_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _medicine_text(med: Medicine) -> str:
    """Build a rich text representation for embedding.

    Combines all searchable fields so the vector captures name, generic
    name, category, brand, form, and strength.
    """
    parts = [med.name]
    if med.generic_name:
        parts.append(med.generic_name)
    if med.strength:
        parts.append(med.strength)
    if med.form:
        parts.append(med.form)
    if med.category_id:
        parts.append(med.category.name)
    if med.brand_id:
        parts.append(med.brand.name)
    if med.description:
        parts.append(med.description[:200])
    return " ".join(parts)


def build_embeddings(force: bool = False) -> int:
    """Encode all active medicines and store vectors.

    Skips medicines whose text hasn't changed (checked via fingerprint)
    unless *force* is True. Returns the number of embeddings created/updated.
    """
    from apps.ai_agent.models import MedicineEmbedding

    medicines = Medicine.objects.filter(is_active=True).select_related("category", "brand")
    texts = [_medicine_text(m) for m in medicines]

    # Batch-encode all texts at once (much faster than one-by-one)
    model = _get_embedder()
    vectors = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)

    created_or_updated = 0
    for med, text, vector in zip(medicines, texts, vectors):
        fp = _text_fingerprint(text)
        embedding, was_created = MedicineEmbedding.objects.get_or_create(
            medicine=med,
            defaults={
                "vector": vector.tolist(),
                "model_name": MODEL_NAME,
                "text_fingerprint": fp,
            },
        )
        if not was_created and (force or embedding.text_fingerprint != fp):
            embedding.vector = vector.tolist()
            embedding.model_name = MODEL_NAME
            embedding.text_fingerprint = fp
            embedding.save(update_fields=["vector", "model_name", "text_fingerprint", "updated_at"])
            created_or_updated += 1
        elif was_created:
            created_or_updated += 1

    logger.info("Built/updated %d medicine embeddings out of %d medicines", created_or_updated, len(medicines))
    return created_or_updated


def search(
    query: str,
    top_k: int = 10,
    min_score: float = 0.35,
) -> list[dict]:
    """Semantic search: encode the query and rank against all medicine vectors.

    Returns a list of dicts: [{"medicine": Medicine, "score": float}, ...]
    sorted by descending cosine similarity.
    """
    from apps.ai_agent.models import MedicineEmbedding

    # Preprocess: detect language, normalise, translate to English
    _normalised, english_query, _lang = preprocess(query)

    # Encode query
    model = _get_embedder()
    query_vec = model.encode([english_query], convert_to_numpy=True)[0]

    # Load all embeddings in one shot
    all_embeddings = MedicineEmbedding.objects.select_related(
        "medicine", "medicine__category", "medicine__brand"
    ).all()

    if not all_embeddings:
        logger.warning("No medicine embeddings found — run `manage.py ai_build_embeddings` first")
        return []

    med_ids = []
    vectors = []
    med_objects = {}
    for emb in all_embeddings:
        med_ids.append(emb.medicine_id)
        vectors.append(emb.get_vector())
        med_objects[emb.medicine_id] = emb.medicine

    matrix = np.stack(vectors)  # (N, 384)
    # Cosine similarity (vectors are already normalised by sentence-transformers)
    scores = matrix @ query_vec  # (N,)

    # Get top-K indices
    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    for idx in top_indices:
        score = float(scores[idx])
        if score < min_score:
            break
        med_id = med_ids[idx]
        results.append({
            "medicine": med_objects[med_id],
            "score": round(score, 4),
        })

    return results


def search_by_category(category_name: str, top_k: int = 20) -> list[dict]:
    """Return all medicines in a category, ranked by relevance to the category name."""
    from apps.ai_agent.models import MedicineEmbedding

    meds = Medicine.objects.filter(
        is_active=True,
        category__name__icontains=category_name,
    ).select_related("category", "brand")[:top_k]

    return [{"medicine": m, "score": 1.0} for m in meds]
