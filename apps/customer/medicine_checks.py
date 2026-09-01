"""
AI copilot safety checks for prescriptions: duplicate-ingredient and
known drug-interaction flags.

These are local, deterministic, zero-dependency rules — the LLM never
invents a safety flag. This module is the single source of truth for
what gets surfaced to the pharmacist during verification.
"""
import re

SEVERITY_HIGH = "high"
SEVERITY_MODERATE = "moderate"

# (keywords_a, keywords_b, severity, title, message)
# Keywords match against the medicine's name AND generic name (lowercased).
INTERACTION_RULES = [
    (
        ["aspirin"], ["ibuprofen", "naproxen", "diclofenac", "mefenamic"],
        SEVERITY_HIGH, "NSAID double-dose",
        "Aspirin plus another NSAID on the same prescription — doubled risk of "
        "stomach bleeding and kidney strain.",
    ),
    (
        ["aspirin"], ["clopidogrel", "warfarin", "apixaban", "rivaroxaban"],
        SEVERITY_HIGH, "Bleeding risk",
        "Aspirin combined with a blood thinner significantly raises the risk of "
        "serious bleeding.",
    ),
    (
        ["ibuprofen", "naproxen", "diclofenac", "mefenamic", "ketorolac"],
        ["ibuprofen", "naproxen", "diclofenac", "mefenamic", "ketorolac"],
        SEVERITY_HIGH, "NSAID double-dose",
        "Two different NSAIDs on the same prescription — confirm the doctor's "
        "intent; risk of stomach ulcers and kidney damage is increased.",
    ),
    (
        ["ciprofloxacin", "moxifloxacin", "levofloxacin", "ofloxacin"],
        ["domperidone", "metoclopramide"],
        SEVERITY_HIGH, "Heart rhythm risk",
        "This fluoroquinolone with domperidone/metoclopramide can prolong the QT "
        "interval — serious cardiac rhythm risk.",
    ),
    (
        ["ciprofloxacin", "moxifloxacin", "levofloxacin", "doxycycline", "tetracycline"],
        ["antacid", "calcium", "iron", "sucralfate"],
        SEVERITY_MODERATE, "Reduced absorption",
        "Antacids and calcium/iron supplements reduce how well this antibiotic is "
        "absorbed — separate the doses by 2 hours.",
    ),
    (
        ["omeprazole", "esomeprazole", "pantoprazole", "lansoprazole"],
        ["clopidogrel"],
        SEVERITY_MODERATE, "Reduced clopidogrel effect",
        "These acid reducers may reduce clopidogrel's anti-clotting effect — "
        "consider replacing with an H2 blocker.",
    ),
    (
        ["salbutamol", "terbutaline"],
        ["atenolol", "propranolol", "bisoprolol", "metoprolol"],
        SEVERITY_MODERATE, "Blunted reliever effect",
        "Beta-blockers can blunt the effect of the asthma reliever — monitor "
        "wheezing carefully.",
    ),
    (
        ["montelukast"], ["aspirin", "ibuprofen", "naproxen", "diclofenac"],
        SEVERITY_MODERATE, "Asthma caution",
        "NSAIDs can worsen asthma symptoms in sensitive patients.",
    ),
    (
        ["escitalopram", "sertraline", "fluoxetine", "citalopram", "paroxetine"],
        ["aspirin", "ibuprofen", "diclofenac", "naproxen"],
        SEVERITY_MODERATE, "Bleeding risk",
        "SSRIs plus NSAIDs raise the risk of gastro-intestinal bleeding.",
    ),
    (
        ["erythromycin", "clarithromycin", "azithromycin"],
        ["domperidone"],
        SEVERITY_HIGH, "Heart rhythm risk",
        "This macrolide with domperidone can prolong the QT interval.",
    ),
    (
        ["metformin"],
        ["iodinated", "contrast"],
        SEVERITY_MODERATE, "Metformin + contrast",
        "Metformin with iodinated contrast dye risks lactic acidosis — hold if a "
        "scan is planned.",
    ),
]

# Words that make a generic-name token meaningful (>= this length counts).
_MIN_TOKEN_LENGTH = 4

_INGREDIENT_SPLIT_RE = re.compile(r"[+\/;,&()]")


def _terms(medicine):
    return f"{medicine.name} {medicine.generic_name or ''}".lower()


def _ingredient_set(medicine):
    text = (medicine.generic_name or medicine.name or "").lower()
    parts = _INGREDIENT_SPLIT_RE.split(text)
    return {p.strip() for p in parts if len(p.strip()) >= _MIN_TOKEN_LENGTH}


def _shared_ingredients(medicine_a, medicine_b):
    return sorted(_ingredient_set(medicine_a) & _ingredient_set(medicine_b))


def _matches(medicine, keywords):
    return any(keyword in _terms(medicine) for keyword in keywords)


def compute_prescription_risks(prescription):
    """Return a deterministic list of risk flags for a prescription.

    Each flag carries:
      severity  — "high" | "moderate" | "info"
      type      — "duplicate" | "interaction"
      title     — short headline for the badge
      message   — plain-language explanation for the pharmacist
      items     — the raw OCR texts of the involved medicine lines
    """
    risks = []
    matched = [item for item in prescription.items.select_related("medicine") if item.medicine_id]
    raw_by_id = {item.id: item.raw_medicine_text for item in matched}

    # 1) Duplicate / shared-ingredient (possible overdose)
    for i in range(len(matched)):
        for j in range(i + 1, len(matched)):
            item_a, item_b = matched[i], matched[j]
            medicine_a, medicine_b = item_a.medicine, item_b.medicine
            shared = _shared_ingredients(medicine_a, medicine_b)
            if not shared:
                continue
            risks.append({
                "severity": SEVERITY_MODERATE,
                "type": "duplicate",
                "title": f"Duplicate ingredient: {shared[0]}",
                "message": (
                    f"{medicine_a.name} and {medicine_b.name} both contain "
                    f"{shared[0]} — possible overdose. Confirm the doctor's intent."
                ),
                "items": [raw_by_id[item_a.id], raw_by_id[item_b.id]],
            })

    # 2) Known interactions between different lines
    for keywords_a, keywords_b, severity, title, message in INTERACTION_RULES:
        a_items = [item for item in matched if _matches(item.medicine, keywords_a)]
        b_items = [item for item in matched if _matches(item.medicine, keywords_b)]
        pairs = set()
        for item_a in a_items:
            for item_b in b_items:
                if item_a.id != item_b.id:
                    pairs.add(tuple(sorted((item_a.id, item_b.id))))
        for pair in sorted(pairs):
            risks.append({
                "severity": severity,
                "type": "interaction",
                "title": title,
                "message": message,
                "items": [raw_by_id[pid] for pid in pair],
            })

    return risks