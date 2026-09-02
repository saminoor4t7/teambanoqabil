"""
Lightweight language detection for the Panda AI chat.

Distinguishes English from Urdu / Roman Urdu so the model can reply in
the user's language. Roman-Urdu is English script with Urdu vocabulary,
so we detect it by counting known Roman-Urdu tokens; actual Urdu script
(\u0600-\u06FF) is detected directly.
"""
import re

_URDU_SCRIPT_RE = re.compile(r"[\u0600-\u06FF]")

# Common Roman-Urdu function words and medical terms.
_ROMAN_URDU_WORDS = {
    "bata", "batao", "batayein", "chaye", "chahiye", "chahiay", "haan", "nai",
    "nahi", "nhi", "nehi", "kya", "kiya", "kis", "kon", "kaun", "kahan", "kahan",
    "kahanse", "kab", "kitna", "kitne", "kitni", "bohot", "bohat", "bahut", "aisa",
    "yahan", "wahan", "mujhe", "mujhy", "mujhay", "hume", "humain", "humay", "tumhe",
    "aap", "apka", "apki", "apko", "apne", "aapka", "aapki", "mein", "main", "mera",
    "meri", "tera", "teri", "hai", "hain", "tha", "thi", "the", "rahi", "rahe",
    "dawa", "dawai", "dawaiyon", "med", "medicine", "dukkan", "dawakhana", "dukan",
    "bukhar", "tap", "sardi", "zukaam", "nazla", "khansi", "dil", "dard", "sir",
    "pet", "paet", "gala", "jism", "kamzor", "thakan", "neend", "khujli", "rash",
    "ultiya", "ulti", "qay", "ishal", "paichish", "shakar", "sugar", "shuger",
    "qeemat", "daam", "dam", "price", "kharidna", "kharhaya",
    "order", "cart", "basket", "add", "yakin", "pata", "maloom", "janna",
}

_LATIN_TOKEN_RE = re.compile(r"[a-z]+")


def is_urdu(text):
    return detect_language(text) == "ur"


def detect_language(text):
    """Return 'ur' when the text looks like Urdu or Roman Urdu, else 'en'."""
    if not text:
        return "en"
    if _URDU_SCRIPT_RE.search(text):
        return "ur"
    tokens = _LATIN_TOKEN_RE.findall(text.lower())
    if not tokens:
        return "en"
    hits = sum(1 for token in tokens if token in _ROMAN_URDU_WORDS)
    # A handful of Urdu tokens (or >= 1/3 of the words) is enough to signal
    # Roman Urdu — English sentences rarely contain these function words.
    if hits >= 3 or hits >= max(1, len(tokens) // 3):
        return "ur"
    return "en"