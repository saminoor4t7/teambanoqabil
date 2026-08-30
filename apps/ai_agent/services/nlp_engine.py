"""
NLP Engine — intent classification + entity extraction.

Two-stage pipeline:
  1. Intent classifier (scikit-learn TF-IDF + LogisticRegression)
     trained on a small seed dataset of pharmacy queries.
  2. Entity extractor (regex + keyword rules) that pulls out
     medicine names, symptoms, dosage info, and patient demographics.

The classifier is intentionally small (< 1 MB) and loads in < 50 ms.
"""

import logging
import re
from pathlib import Path

import numpy as np
from joblib import dump as joblib_dump
from joblib import load as joblib_load
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parent.parent / "ml_models"

# ── Intent labels ──────────────────────────────────────────────────────
INTENTS = [
    "medicine_search",   # "find me paracetamol"
    "category_browse",   # "show me pain killers"
    "medicine_info",     # "what is amoxicillin used for"
    "image_match",       # "match this photo" / "is ye dawai"
    "order_status",      # "where is my order"
    "general",           # chit-chat, greetings
]

# ── Seed training data (expand over time) ─────────────────────────────
# Each tuple: (example_utterance, intent_label)
SEED_DATA: list[tuple[str, str]] = [
    # medicine_search
    ("find paracetamol 500mg", "medicine_search"),
    ("mujhe panadol chahiye", "medicine_search"),
    ("i need amoxicillin", "medicine_search"),
    ("sar dard ki dawai", "medicine_search"),
    ("do you have flagyl", "medicine_search"),
    ("looking for insulin", "medicine_search"),
    ("buy augmentin 625", "medicine_search"),
    ("bukhar ki tablet", "medicine_search"),
    ("medicine for cough", "medicine_search"),
    ("khansi ki sharbat", "medicine_search"),
    ("i want to order medicine", "medicine_search"),
    ("metformin 500mg available hai", "medicine_search"),
    # category_browse
    ("show me pain killers", "category_browse"),
    ("antibiotics category", "category_browse"),
    ("dard ki dawai dikhao", "category_browse"),
    ("heart medicines", "category_browse"),
    ("vitamins and supplements", "category_browse"),
    ("skin care products", "category_browse"),
    ("bachon ki dawai", "category_browse"),
    ("diabetes medicines list", "category_browse"),
    # medicine_info
    ("what is amoxicillin used for", "medicine_info"),
    ("paracetamol ke side effects", "medicine_info"),
    ("how to take metformin", "medicine_info"),
    ("augmentin ki dose kya hai", "medicine_info"),
    ("is flagyl safe for children", "medicine_info"),
    ("panadol ka kaam kya hai", "medicine_info"),
    ("tell me about ibuprofen", "medicine_info"),
    # image_match
    ("match this medicine photo", "image_match"),
    ("ye konsi dawai hai", "image_match"),
    ("identify this tablet", "image_match"),
    ("scan this medicine", "image_match"),
    ("check this prescription image", "image_match"),
    ("is ye medicine hai", "image_match"),
    ("photo se dawai pehchano", "image_match"),
    # order_status
    ("where is my order", "order_status"),
    ("mera order kahan hai", "order_status"),
    ("order status check", "order_status"),
    ("kab tak aaye ga order", "order_status"),
    ("track my delivery", "order_status"),
    ("is my order delivered", "order_status"),
    # general
    ("hello", "general"),
    ("hi", "general"),
    ("assalam o alaikum", "general"),
    ("thank you", "general"),
    ("shukriya", "general"),
    ("help me please", "general"),
    ("kya aap madad kar sakte hain", "general"),
]


class IntentClassifier:
    """TF-IDF + LogisticRegression intent classifier.

    Trains on SEED_DATA at first run and pickles the model to disk.
    Subsequent loads read the pickle — retrain by calling .train() again.
    """

    def __init__(self):
        self.pipeline: Pipeline | None = None
        self._model_path = MODEL_DIR / "intent_classifier.pkl"

    def train(self, extra_data: list[tuple[str, str]] | None = None) -> None:
        """Train (or retrain) the classifier and persist to disk."""
        data = SEED_DATA + (extra_data or [])
        texts, labels = zip(*data)

        self.pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(
                ngram_range=(1, 2),
                max_features=5000,
                sublinear_tf=True,
            )),
            ("clf", LogisticRegression(
                max_iter=500,
                C=2.0,
                class_weight="balanced",
            )),
        ])
        self.pipeline.fit(texts, labels)

        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        # Persist with joblib (sklearn's recommended serialiser).
        # The file is only ever loaded from MODEL_DIR — never from
        # user uploads, network sources, or untrusted caches.
        joblib_dump(self.pipeline, self._model_path, compress=3)
        logger.info("Intent classifier trained and saved to %s", self._model_path)

    def load(self) -> bool:
        """Load a previously trained model from disk. Returns True if loaded."""
        if self._model_path.exists():
            # Security: only load from the trusted local model directory.
            resolved = self._model_path.resolve()
            trusted = MODEL_DIR.resolve()
            if not str(resolved).startswith(str(trusted)):
                logger.error("Refusing to load model from untrusted path: %s", resolved)
                return False
            self.pipeline = joblib_load(resolved)
            logger.info("Intent classifier loaded from %s", self._model_path)
            return True
        logger.warning("No trained intent classifier found at %s", self._model_path)
        return False

    def predict(self, text: str) -> tuple[str, float]:
        """Return (intent_label, confidence).

        Falls back to keyword heuristics if no model is loaded.
        """
        if self.pipeline is not None:
            proba = self.pipeline.predict_proba([text])[0]
            idx = int(np.argmax(proba))
            label = self.pipeline.classes_[idx]
            return label, float(proba[idx])
        return self._fallback_predict(text)

    @staticmethod
    def _fallback_predict(text: str) -> tuple[str, float]:
        """Keyword-based fallback when no trained model exists yet."""
        lower = text.lower()
        if any(w in lower for w in ("order", "delivery", "track", "kab tak")):
            return "order_status", 0.6
        if any(w in lower for w in ("photo", "image", "scan", "ye konsi", "pehchano")):
            return "image_match", 0.6
        if any(w in lower for w in ("what is", "kya hai", "side effect", "dose", "kaam")):
            return "medicine_info", 0.6
        if any(w in lower for w in ("category", "list", "types", "dikhao", "show")):
            return "category_browse", 0.5
        if any(w in lower for w in ("find", "buy", "need", "chahiye", "available", "order")):
            return "medicine_search", 0.5
        return "general", 0.3


# ── Entity extraction ──────────────────────────────────────────────────

# Common dosage patterns: "500mg", "10 ml", "250 mg"
DOSAGE_RE = re.compile(r"\b(\d{1,4})\s*(mg|ml|mcg|g|iu|iu|units?)\b", re.I)
# Quantity patterns: "2 strips", "1 bottle", "30 tablets"
QUANTITY_RE = re.compile(r"\b(\d+)\s*(strip|strips|bottle|bottles|tablet|tablets|box|boxes|pack|packs)\b", re.I)
# Age group keywords
AGE_GROUPS = {
    "child": ["bachon", "bacha", "child", "children", "kids", "baby", "infant"],
    "adult": ["baron", "adult", "adults"],
    "elderly": ["buzurg", "elderly", "senior", "old age"],
}
# Form keywords
FORM_KEYWORDS = {
    "tablet": ["tablet", "goli", "tab", "cap", "capsule"],
    "syrup": ["syrup", "sharbat", "liquid", "suspension"],
    "injection": ["injection", "teeka", "ampoule"],
    "cream": ["cream", "malham", "ointment", "gel", "lotion"],
    "drops": ["drops", "qatray"],
}


def extract_entities(text: str) -> dict:
    """Extract structured entities from a user query.

    Returns a dict with keys: medicines, dosages, quantities, form, age_group, symptoms.
    """
    lower = text.lower()
    entities: dict = {
        "medicines": [],
        "dosages": [],
        "quantities": [],
        "form": None,
        "age_group": None,
        "symptoms": [],
    }

    # Dosages
    for match in DOSAGE_RE.finditer(lower):
        entities["dosages"].append(f"{match.group(1)}{match.group(2)}")

    # Quantities
    for match in QUANTITY_RE.finditer(lower):
        entities["quantities"].append({"count": int(match.group(1)), "unit": match.group(2)})

    # Form
    for form, keywords in FORM_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            entities["form"] = form
            break

    # Age group
    for group, keywords in AGE_GROUPS.items():
        if any(kw in lower for kw in keywords):
            entities["age_group"] = group
            break

    return entities


# ── Module-level singleton ─────────────────────────────────────────────
_classifier: IntentClassifier | None = None


def get_classifier() -> IntentClassifier:
    """Return the shared classifier instance, loading or training as needed."""
    global _classifier
    if _classifier is None:
        _classifier = IntentClassifier()
        if not _classifier.load():
            _classifier.train()
    return _classifier
