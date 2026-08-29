"""
Roman Urdu ↔ English language detection and normalisation.

The agent accepts input in English or Roman Urdu (e.g. "sar dard ki dawai").
This module:
  1. Detects which language the user wrote.
  2. Normalises common Roman Urdu spellings so the NLP engine sees
     consistent tokens ("dawai" / "dawaai" → "dawai").
  3. Provides a bilingual synonym map so Urdu medicine terms can be
     matched against the English-language catalog.
"""

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

# ── Roman Urdu → English medicine / symptom synonyms ──────────────────
# This map grows over time; it's the cheapest way to bridge the vocabulary
# gap between what customers say and what the catalog stores.
ROMAN_URDU_SYNONYMS: dict[str, str] = {
    # symptoms
    "bukhar": "fever",
    "tap": "fever",
    "sar dard": "headache",
    "sir dard": "headache",
    "pait dard": "stomach ache",
    "pait mein dard": "stomach ache",
    "khansi": "cough",
    "zukam": "cold",
    "naak band": "nasal congestion",
    "gala kharab": "sore throat",
    "dard": "pain",
    "sujan": "swelling",
    "infection": "infection",
    "ulti": "vomiting",
    "qabz": "constipation",
    "dast": "diarrhea",
    "chakkar": "dizziness",
    "bechaini": "anxiety",
    "neend na aana": "insomnia",
    # medicine forms
    "dawai": "medicine",
    "dawaai": "medicine",
    "dawa": "medicine",
    "tablet": "tablet",
    "goli": "tablet",
    "sharbat": "syrup",
    "syrup": "syrup",
    "teeka": "injection",
    "injection": "injection",
    "cream": "cream",
    "malham": "ointment",
    "ointment": "ointment",
    "drops": "drops",
    "qatray": "drops",
    # categories
    "bachon ki dawai": "pediatric medicine",
    "dil ki dawai": "heart medicine",
    "blood pressure": "blood pressure",
    "sugar ki dawai": "diabetes medicine",
    # common modifiers
    "bache": "children",
    "bachon": "children",
    "baron": "adults",
    "aurat": "women",
    "mard": "men",
    "subah": "morning",
    "shaam": "evening",
    "raat": "night",
    "khana": "food",
    "khali pait": "empty stomach",
}

# ── Spelling normalisation (common Roman Urdu variations) ─────────────
SPELLING_MAP: dict[str, str] = {
    "dawaai": "dawai",
    "davaai": "dawai",
    "dava": "dawai",
    "bukhar": "bukhar",
    "bokhar": "bukhar",
    "zukam": "zukam",
    "zukaam": "zukam",
    "khansi": "khansi",
    "khanshi": "khansi",
    "sirdard": "sar dard",
    "sirdard": "sar dard",
    "paitdard": "pait dard",
}


def detect_language(text: str) -> str:
    """Return 'en', 'roman_ur', or 'mixed'.

    Uses a lightweight keyword heuristic first (fast, no deps), falling
    back to langdetect for ambiguous input.
    """
    lower = text.lower()
    urdu_tokens = set(ROMAN_URDU_SYNONYMS.keys()) | set(SPELLING_MAP.keys())
    words = set(lower.split())

    urdu_hits = words & urdu_tokens
    # Multi-word phrase matching (e.g. "sar dard" is two tokens)
    for phrase in urdu_tokens:
        if " " in phrase and phrase in lower:
            urdu_hits.add(phrase)

    if not urdu_hits:
        return "en"

    # If > 40 % of meaningful tokens are Urdu → Roman Urdu
    meaningful = words - {"a", "an", "the", "is", "are", "was", "for", "and", "or", "of", "to", "me", "ko", "ka", "ki", "hai", "tha", "ho", "hoon"}
    if not meaningful:
        return "en"

    ratio = len(urdu_hits) / len(meaningful)
    if ratio > 0.4:
        return "roman_ur"
    if urdu_hits:
        return "mixed"
    return "en"


def normalise_roman_urdu(text: str) -> str:
    """Apply spelling normalisation to Roman Urdu tokens in *text*."""
    words = text.lower().split()
    normalised = [SPELLING_MAP.get(w, w) for w in words]
    return " ".join(normalised)


def translate_to_english(text: str) -> str:
    """Replace known Roman Urdu terms with English equivalents.

    Handles both single-word and multi-word phrases (longest-match first).
    Unknown words are left as-is — the sentence-transformer model is
    multilingual and can still extract useful signal.
    """
    lower = text.lower()
    # Sort phrases longest-first so "sar dard" matches before "sar"
    phrases = sorted(ROMAN_URDU_SYNONYMS.keys(), key=len, reverse=True)
    for phrase in phrases:
        if phrase in lower:
            lower = lower.replace(phrase, ROMAN_URDU_SYNONYMS[phrase])
    return lower


@lru_cache(maxsize=256)
def preprocess(text: str) -> tuple[str, str, str]:
    """Full preprocessing pipeline.

    Returns (normalised_text, english_translation, detected_language).
    """
    lang = detect_language(text)
    normalised = normalise_roman_urdu(text) if lang != "en" else text.lower()
    english = translate_to_english(normalised) if lang != "en" else normalised
    return normalised, english, lang
