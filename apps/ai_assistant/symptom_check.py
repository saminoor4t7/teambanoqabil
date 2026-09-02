"""
Local symptom triage powering the Panda AI `symptom_check` tool.

Deterministic, rule-based (no LLM dependency): maps common Pakistani
symptoms to a condition, recommends OTC medicines that exist in the
catalog, flags when a doctor visit is needed, and asks a follow-up
question when the picture is unclear.
"""
from apps.catalog.models import Medicine

from .tools import _pharmacy


SYMPTOM_CONDITIONS = {
    "fever": {
        "label": "Fever & body temperature",
        "keywords": ["fever", "bukhar", "temperature", "tap", "viral", "thal"],
        "follow_up": "How long have you had the fever, and what is the temperature?",
        "medicine_names": ["Panadol", "Brufen", "Calpol"],
        "advice": "Paracetamol is the first-line fever reliever for adults. Stay hydrated and rest.",
        "doctor_visit": False,
    },
    "cold_flu": {
        "label": "Cold, flu & runny nose",
        "keywords": ["cold", "flu", "sardi", "zukaam", "nazla", "runny nose", "sneezing", "chheenk", "shivering"],
        "follow_up": "Do you have a fever or body ache alongside the cold?",
        "medicine_names": ["Panadol", "Rigix", "Lora", "Decoflam"],
        "advice": "Rest, warm fluids, and an antihistamine/decongestant usually settle common cold symptoms.",
        "doctor_visit": False,
    },
    "cough": {
        "label": "Cough",
        "keywords": ["cough", "khansi", "dry cough", "wet cough", "productive cough"],
        "follow_up": "Is the cough dry or productive (with phlegm), and has it lasted more than a week?",
        "medicine_names": ["Benadryl", "Decoflam"],
        "advice": "Honey and warm fluids help a cough. If it persists beyond a week or you cough up blood, "
                  "you need a doctor.",
        "doctor_visit": False,
    },
    "headache": {
        "label": "Headache / migraine",
        "keywords": ["headache", "sir dard", "migraine", "head pain", "sir"],
        "follow_up": "Is the headache one-sided, throbbing, or accompanied by nausea?",
        "medicine_names": ["Panadol Extra", "Panadol", "Brufen"],
        "advice": "Rest in a quiet dark room and take a simple analgesic. Sudden 'worst-ever' headaches "
                  "need urgent medical attention.",
        "doctor_visit": False,
    },
    "body_pain": {
        "label": "Body & muscle pain",
        "keywords": ["body pain", "muscle pain", "jism dard", "chan", "sprain", "joint pain", "jora dard"],
        "follow_up": "Where is the pain and how long has it been present?",
        "medicine_names": ["Brufen", "Panadol", "Volini Gel"],
        "advice": "Apply ice/heat as appropriate and use an NSAID or topical gel short-term.",
        "doctor_visit": False,
    },
    "acidity": {
        "label": "Acidity, gas & heartburn",
        "keywords": ["acidity", "gas", "heartburn", "gastro", "khatara", "paat", "reflux", "bloating", "paet"],
        "follow_up": "Do you get it after meals, at night, or both?",
        "medicine_names": ["Gaviscon", "Motilium"],
        "advice": "Smaller meals, avoiding late-night eating and spicy food, and an antacid usually helps. "
                  "Persistent reflux deserves a doctor's review (Rx acid-reducers are available).",
        "doctor_visit": False,
    },
    "nausea": {
        "label": "Nausea & vomiting",
        "keywords": ["nausea", "vomiting", "ulti", "qay", "sick stomach"],
        "follow_up": "How long have you been nauseous, and can you keep fluids down?",
        "medicine_names": ["Motilium", "Smecta"],
        "advice": "Sip fluids slowly and take an anti-nausea medicine if needed. Inability to keep water "
                  "down warrants medical attention.",
        "doctor_visit": False,
    },
    "diarrhea": {
        "label": "Diarrhoea",
        "keywords": ["diarrhea", "loose motion", "diarrhoea", "ishal", "paichish", "paet dard"],
        "follow_up": "Is there blood in the stool, and are you able to keep fluids down?",
        "medicine_names": ["Smecta", "Imodium"],
        "advice": "The priority is rehydration (ORS). Love-motion relievers are fine for short episodes; "
                  "blood or dehydration needs a doctor.",
        "doctor_visit": False,
    },
    "allergy": {
        "label": "Allergy & itching",
        "keywords": ["allergy", "itch", "khujli", "rash", "urticaria", "hives", "chakay", "sneezing"],
        "follow_up": "How severe is the itching or rash, and did it start after a new soap, food or medicine?",
        "medicine_names": ["Rigix", "Lora", "Allegra"],
        "advice": "Avoid the trigger and use a non-drowsy antihistamine. A severe reaction with breathing "
                  "trouble is an emergency.",
        "doctor_visit": False,
    },
    "sore_throat": {
        "label": "Sore throat",
        "keywords": ["sore throat", "gala dard", "throat pain", "gala khrab"],
        "follow_up": "Do you have a fever, white spots on the tonsils, or difficulty swallowing?",
        "medicine_names": ["Panadol", "Panadol Extra"],
        "advice": "Warm salt-water gargles and an analgesic help. Persistent pain with fever can be "
                  "strep — see a doctor for antibiotics.",
        "doctor_visit": False,
    },
    "sleep_anxiety": {
        "label": "Sleep & stress",
        "keywords": ["sleep", "insomnia", "neend", "anxiety", "tanhai", "stress", "depression", "sad", "garmi"],
        "follow_up": "How long have you been struggling with sleep or stress, and is it affecting your day?",
        "medicine_names": [],
        "advice": "Sleep hygiene and talking to someone help most cases. Medicines for anxiety or sleep "
                  "are prescription-only and should be guided by a psychiatrist.",
        "doctor_visit": True,
    },
    "diabetes": {
        "label": "Blood sugar",
        "keywords": ["diabetes", "shakar", "sugar", "sweet urine", "shuger"],
        "follow_up": "What is your latest fasting or random blood sugar reading?",
        "medicine_names": [],
        "advice": "Blood-sugar medicines are prescription-only. Please share your latest readings and "
                  "get a doctor's review.",
        "doctor_visit": True,
    },
}

# Urgent symptoms that always escalate to 'see a doctor' even when a
# benign condition also matches.
RED_FLAG_KEYWORDS = [
    "chest pain", "sina dard", "breathless", "breathing trouble", "sans",
    "faint", "unconscious", "blood in", "bloody", "khun", "seizure",
    "attack", "serious", "worse", "pregnancy", "pregnant", "suicidal",
]


def triage_symptoms(text):
    """Score free-text symptoms against the local knowledge base.

    Returns (condition_key, score, red_flag_text or None).
    """
    haystack = text.lower().strip()

    # Roman-Urdu is written in English letters, so keyword matching already
    # catches it; the model decides the reply language from detect_language().
    best_key, best_score = None, 0
    for key, condition in SYMPTOM_CONDITIONS.items():
        score = sum(1 for kw in condition["keywords"] if kw in haystack)
        if score > best_score:
            best_key, best_score = key, score

    for flag in RED_FLAG_KEYWORDS:
        if flag in haystack:
            return best_key, best_score, (
                f"Your description includes a red-flag sign ({flag}) — please "
                "see a doctor or visit the emergency department promptly."
            )

    return best_key, best_score, None


def _inventory_object(medicine, pharmacy):
    from apps.medical_store.models import InventoryItem
    return InventoryItem.objects.filter(pharmacy=pharmacy, medicine=medicine).first() if pharmacy else None


def _decorate(medicine, pharmacy, pharmacy_name):
    inv = _inventory_object(medicine, pharmacy)
    stock = int(inv.quantity_in_stock or 0) if inv else 0
    return {
        "id": medicine.id,
        "name": medicine.name,
        "generic_name": medicine.generic_name,
        "strength": medicine.strength,
        "form": medicine.form,
        "requires_prescription": medicine.requires_prescription,
        "description": (medicine.description[:120] if medicine.description else ""),
        "price": float(inv.selling_price) if inv else 0,
        "stock": stock,
        "available": bool(inv) and stock > 0,
        "pharmacy": pharmacy_name if inv else "",
    }


def symptom_check(customer, args):
    """Tool for the AI: triage symptoms and recommend available medicines."""
    symptoms = (args.get("symptoms") or args.get("query") or "").strip()
    if not symptoms:
        return {
            "needs_clarification": True,
            "question": "Please describe your symptoms, for example: 'fever and cough since two days'.",
        }

    key, score, red_flag = triage_symptoms(symptoms)

    if key is None or score == 0:
        return {
            "needs_clarification": True,
            "question": (
                "I'd like to help but I need a bit more detail — what symptoms are you feeling "
                "(fever, cough, headache, acidity, allergy, etc.), and how long have you had them?"
            ),
        }

    condition = SYMPTOM_CONDITIONS[key]
    pharmacy = _pharmacy(customer)
    pharmacy_name = pharmacy.business_name if pharmacy else "No pharmacy selected"

    medicines = []
    if condition["medicine_names"]:
        for med in Medicine.objects.filter(
            is_active=True, name__in=condition["medicine_names"]
        ).order_by("name"):
            medicines.append(_decorate(med, pharmacy, pharmacy_name))

    return {
        "condition": key,
        "label": condition["label"],
        "needs_clarification": False,
        "follow_up_question": condition["follow_up"],
        "advice": condition["advice"],
        "doctor_visit": condition["doctor_visit"] or bool(red_flag),
        "red_flag": red_flag,
        "red_flag_text": red_flag,
        "medicines": medicines,
        "found": len(medicines),
        "pharmacy": pharmacy_name,
    }