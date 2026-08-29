"""
Image Analyzer — extract visual features from medicine photos and match
them against stored medicine image embeddings.

Approach (lightweight, no external API):
  1. Colour histogram — captures the dominant colours on the packaging.
  2. Perceptual hash (pHash) — captures the overall shape/layout.
  3. Both are combined into a single feature vector and compared via
     cosine similarity.

This is intentionally simple: it won't read text off a box (that's the
OCR microservice's job), but it can quickly say "this photo looks most
like Panadol packaging" from the catalog.
"""

import io
import logging

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# ── Feature extraction ────────────────────────────────────────────────

HIST_BINS = 32          # bins per channel (R, G, B)
IMAGE_SIZE = (128, 128)  # resize for consistent feature extraction


def _load_image(image_data: bytes | Image.Image) -> Image.Image:
    """Accept raw bytes or a PIL Image and return an RGB PIL Image."""
    if isinstance(image_data, Image.Image):
        return image_data.convert("RGB")
    return Image.open(io.BytesIO(image_data)).convert("RGB")


def extract_colour_histogram(img: Image.Image) -> np.ndarray:
    """3-channel colour histogram, normalised to unit length."""
    img_resized = img.resize(IMAGE_SIZE)
    channels = img_resized.split()
    histograms = []
    for ch in channels:
        hist = np.array(ch.histogram(bins=HIST_BINS), dtype=np.float32)
        norm = np.linalg.norm(hist)
        if norm > 0:
            hist /= norm
        histograms.append(hist)
    return np.concatenate(histograms)  # (96,)


def extract_phash(img: Image.Image) -> np.ndarray:
    """Perceptual hash as a binary feature vector (256 bits).

    Simple average-hash: resize to 16×16, convert to grayscale,
    compare each pixel to the mean.
    """
    gray = img.resize((16, 16)).convert("L")
    pixels = np.array(gray, dtype=np.float32)
    mean = pixels.mean()
    bits = (pixels > mean).flatten().astype(np.float32)  # (256,)
    return bits


def extract_features(img: Image.Image) -> np.ndarray:
    """Combined feature vector: colour histogram + perceptual hash.

    Returns a float32 vector of length 352 (96 + 256).
    """
    colour = extract_colour_histogram(img)
    phash = extract_phash(img)
    return np.concatenate([colour, phash])


def compute_image_embedding(image_data: bytes | Image.Image) -> np.ndarray:
    """Public entry point: bytes or PIL Image → feature vector."""
    img = _load_image(image_data)
    return extract_features(img)


def build_medicine_image_embedding(image_data: bytes | Image.Image) -> list[float]:
    """Compute and return a JSON-serialisable image embedding."""
    vec = compute_image_embedding(image_data)
    return vec.tolist()


# ── Matching ──────────────────────────────────────────────────────────

def match_image(image_data: bytes | Image.Image, top_k: int = 5, min_score: float = 0.5) -> list[dict]:
    """Match a medicine photo against stored image embeddings.

    Returns [{"medicine": Medicine, "score": float}, ...] sorted by
    descending similarity.
    """
    from apps.ai_agent.models import MedicineEmbedding

    query_vec = compute_image_embedding(image_data)

    embeddings = MedicineEmbedding.objects.filter(
        image_embedding__isnull=False,
    ).select_related("medicine", "medicine__category", "medicine__brand")

    if not embeddings:
        logger.warning("No image embeddings in DB — run build with --images flag")
        return []

    med_ids = []
    vectors = []
    med_objects = {}
    for emb in embeddings:
        img_vec = emb.get_image_embedding()
        if img_vec is not None and len(img_vec) == len(query_vec):
            med_ids.append(emb.medicine_id)
            vectors.append(img_vec)
            med_objects[emb.medicine_id] = emb.medicine

    if not vectors:
        return []

    matrix = np.stack(vectors)
    scores = matrix @ query_vec  # cosine similarity (vectors are normalised)

    top_indices = np.argsort(scores)[::-1][:top_k]
    results = []
    for idx in top_indices:
        score = float(scores[idx])
        if score < min_score:
            break
        results.append({
            "medicine": med_objects[med_ids[idx]],
            "score": round(score, 4),
        })

    return results
