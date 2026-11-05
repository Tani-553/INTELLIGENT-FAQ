"""
query_processor.py
------------------
Turns a natural-language question into a LOGICAL QUERY.
It is deterministic pattern matching (regular expressions + small word lists).
It does NOT answer anything - it only decides what to ask the inference engine.

Result of parse_question():
    {
      "status":   "ok" | "empty" | "medical" | "unknown",
      "intent":   e.g. "FIND_DOCTOR_BY_SPECIALIZATION",
      "entities": e.g. {"department": "cardiology"},
      "query":    ("specializes", ["Doctor", "cardiology"])   # capital = variable
    }
"""

import re

import knowledge_base as kb

HOSPITAL = "citycare_hospital"

# ---------------------------------------------------------------- vocabulary
# words people use  ->  constant used in the knowledge base
DEPARTMENT_WORDS = {
    "cardiology": "cardiology", "cardiologist": "cardiology", "cardiologists": "cardiology",
    "neurology": "neurology", "neurologist": "neurology", "neurologists": "neurology",
    "orthopedics": "orthopedics", "orthopaedics": "orthopedics", "orthopedic": "orthopedics",
    "orthopaedic": "orthopedics", "orthopedist": "orthopedics", "orthopedists": "orthopedics",
    "pediatrics": "pediatrics", "paediatrics": "pediatrics", "pediatrician": "pediatrics",
    "paediatrician": "pediatrics", "pediatricians": "pediatrics",
    "dermatology": "dermatology", "dermatologist": "dermatology", "dermatologists": "dermatology",
    "general medicine": "general_medicine", "general physician": "general_medicine",
    "ent": "ent",
}
# words that name a PERSON'S job ("the neurologist") rather than a department
TITLE_WORDS = {w for w in DEPARTMENT_WORDS
               if w.endswith(("ist", "ists", "ician", "icians")) or w == "general physician"}

FACILITY_WORDS = {
    "mri": "mri", "ct scan": "ct_scan", "ct-scan": "ct_scan", "ctscan": "ct_scan",
    "x-ray": "xray", "xray": "xray", "x ray": "xray",
    "laboratory": "laboratory", "lab": "laboratory",
    "pharmacy": "pharmacy", "blood bank": "blood_bank", "icu": "icu",
    "intensive care": "icu", "intensive care unit": "icu",
    "ambulance": "ambulance", "ambulance service": "ambulance",
}

SERVICE_WORDS = {
    "radiology": "radiology", "opd": "opd", "outpatient": "opd",
    "laboratory testing": "laboratory_testing", "lab testing": "laboratory_testing",
    "lab tests": "laboratory_testing", "pharmacy": "pharmacy",
    "inpatient care": "inpatient_care", "inpatient": "inpatient_care",
    "admission": "inpatient_care", "surgery": "surgery", "surgical": "surgery",
}

# Questions that ask for medical advice are refused (this is not a medical system).
MEDICAL_ADVICE_PATTERN = re.compile(
    r"\b(diagnos\w*|treatments?|medicines?|medications?|dosages?|doses?|prescri\w*|symptoms?|"
    r"cures?|remed(?:y|ies)|what should i take|do i have|am i having|"
    r"my (?:pain|fever|headache|cough|chest))\b")


# ---------------------------------------------------------------- helpers

def _clean(text):
    """lower-case, remove punctuation and extra spaces"""
    text = text.lower().replace("?", " ").replace("!", " ").replace(",", " ")
    text = re.sub(r"[^a-z0-9\s\-\.]", " ", text)
    text = re.sub(r"(?<![a-z])dr\.", "dr ", text)          # "Dr.Arun" -> "dr arun"
    return re.sub(r"\s+", " ", text).strip()


def _find(words, q):
    """Return (word, constant) for the first vocabulary word found in q (longest words first)."""
    for word in sorted(words, key=len, reverse=True):
        if re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", q):
            return word, words[word]
    return None, None


def _result(intent, entities, predicate, args):
    return {"status": "ok", "intent": intent, "entities": entities, "query": (predicate, args)}


def _unknown(status="unknown"):
    return {"status": status, "intent": None, "entities": {}, "query": None}


def _name_after(pattern, q):
    """Pick a doctor's name out of the question, ignoring filler words."""
    match = re.search(pattern, q)
    if match and match.group(1) not in {"the", "a", "an", "this", "hospital", "doctor"}:
        return match.group(1)
    return None


def _normalize_keyword(value):
    return re.sub(r"[_\-]+", " ", str(value).lower()).strip()


def _phrase_pattern(phrase):
    phrase = re.escape(phrase)
    phrase = phrase.replace(r"\ ", r"(?:[ _-]+)")
    return r"(?<![a-z0-9])" + phrase + r"(?![a-z0-9])"


def _has_phrase(q, phrase):
    phrase = (phrase or "").strip()
    if not phrase:
        return False
    return bool(re.search(_phrase_pattern(phrase), q))


def _keyword_score(q, phrases):
    score = 0
    for phrase in sorted({p for p in phrases if p}, key=len, reverse=True):
        if _has_phrase(q, phrase):
            score += 1 + max(0, len(phrase.split()) - 1)
    return score


def _dynamic_keyword_aliases():
    aliases = {
        "doctor": set(),
        "department": set(),
        "service": set(),
        "facility": set(),
    }
    try:
        facts = kb.load_facts()
    except Exception:
        return aliases

    for fact in facts:
        predicate = fact.get("predicate")
        args = fact.get("args", [])
        if predicate not in aliases:
            continue
        for value in args:
            normalized = _normalize_keyword(value)
            if not normalized:
                continue
            aliases[predicate].add(normalized)
            if "_" in value:
                aliases[predicate].add(value.replace("_", " "))
    return aliases


def _extract_named_entity(q, candidates):
    for candidate in sorted(candidates, key=len, reverse=True):
        if _has_phrase(q, candidate):
            return _normalize_keyword(candidate)
    return None


def _detect_keyword_intent(q, aliases):
    # Generic hint words are intentionally weak; they are only used alongside a
    # category-specific keyword or entity name. This keeps generic words such as
    # "hospital", "show", or "what" from being treated as standalone intent.
    service_words = {"service", "services", "provide", "provided", "provides", "offering",
                     "offer", "offers", "offered"}
    timing_words = {"timing", "timings", "time", "hours", "opening", "open", "closing",
                    "close", "working hours", "availability", "available", "when", "schedule"}
    doctor_words = {"doctor", "doctors", "physician", "physicians", "specialist",
                    "specialists", "surgeon", "surgeons", "dr"}
    department_words = {"department", "departments", "specialty", "specialties",
                        "specialization", "specializations"}
    facility_words = {"facility", "facilities", "mri", "ct scan", "ctscan", "xray",
                      "x-ray", "lab", "laboratory", "blood bank", "icu", "ambulance"}
    emergency_words = {"emergency", "urgent care", "casualty", "emergency service"}

    dynamic_service = aliases.get("service", set())
    dynamic_department = aliases.get("department", set())
    dynamic_facility = aliases.get("facility", set())
    dynamic_doctor = aliases.get("doctor", set())

    department_entity = _extract_named_entity(q, set(DEPARTMENT_WORDS.values()) | dynamic_department)
    facility_entity = _extract_named_entity(q, set(FACILITY_WORDS.values()) | dynamic_facility)
    service_entity = _extract_named_entity(q, set(SERVICE_WORDS.values()) | dynamic_service)
    doctor_entity = _extract_named_entity(q, dynamic_doctor)

    dept_score = _keyword_score(q, department_words | dynamic_department)
    service_score = _keyword_score(q, service_words | dynamic_service)
    facility_score = _keyword_score(q, facility_words | dynamic_facility)
    timing_score = _keyword_score(q, timing_words)
    doctor_score = _keyword_score(q, doctor_words | dynamic_doctor)
    emergency_score = _keyword_score(q, emergency_words)

    if service_score and (
            re.search(r"\b(?:provide|provided|provides|offering|offer|offers|offered|service|services)\b", q)
            or (re.search(r"\b(?:service|services)\b", q) and re.search(r"\b(?:available|offered|provided|provide)\b", q))
            or re.search(r"\b(?:hospital|citycare)\b", q)
    ):
        return _result("LIST_SERVICES", {}, "available_service", [HOSPITAL, "Service"])

    if doctor_score and timing_score and doctor_entity:
        return _result("FIND_DOCTOR_AVAILABILITY", {"doctor": doctor_entity},
                       "doctor_available", [doctor_entity, "Timing"])

    if department_entity and doctor_score and re.search(r"\b(?:specializ\w*|specialis\w*|works? in|work\s+in|department)\b", q):
        return _result("FIND_DOCTOR_BY_SPECIALIZATION", {"department": department_entity},
                       "specializes", ["Doctor", department_entity])

    if facility_entity and (re.search(r"\b(?:hospital|citycare)\b", q) or re.search(r"\b(?:have|has|available|provide|provides|offering|offer)\b", q)):
        if re.search(r"\b(?:list|show|which|what|all)\b", q):
            return _result("LIST_FACILITIES", {}, "available_facility", [HOSPITAL, "Facility"])
        return _result("CHECK_FACILITY", {"facility": facility_entity},
                       "available_facility", [HOSPITAL, facility_entity])

    if re.search(r"\b(?:opd|outpatient)\b", q) and timing_score:
        return _result("FIND_OPD_TIMING", {}, "opd_timing", [HOSPITAL, "Timing"])

    if re.search(r"\b(?:hospital|citycare)\b", q) and timing_score:
        return _result("FIND_HOSPITAL_TIMING", {}, "hospital_open", [HOSPITAL, "Timing"])

    if dept_score and re.search(r"\b(?:list|show|which|what|all|available)\b", q):
        return _result("LIST_DEPARTMENTS", {}, "department", ["Department"])

    if emergency_score and re.search(r"\b(?:service|services|available|help)\b", q):
        return _result("CHECK_EMERGENCY", {}, "emergency_ready", [HOSPITAL])

    if doctor_entity and re.search(r"\b(?:available|availability|hours|timing|schedule|visit|visiting)\b", q):
        return _result("FIND_DOCTOR_AVAILABILITY", {"doctor": doctor_entity},
                       "doctor_available", [doctor_entity, "Timing"])

    if facility_entity and re.search(r"\b(?:list|show|which|what|all)\b", q):
        return _result("LIST_FACILITIES", {}, "available_facility", [HOSPITAL, "Facility"])

    if service_entity and re.search(r"\b(?:list|show|which|what|all)\b", q):
        return _result("LIST_SERVICES", {}, "available_service", [HOSPITAL, "Service"])

    if department_entity and re.search(r"\b(?:doctors?|specialist|physician|surgeon)\b", q):
        return _result("FIND_DOCTOR_BY_SPECIALIZATION", {"department": department_entity},
                       "specializes", ["Doctor", department_entity])

    return None


# ---------------------------------------------------------------- main function

def parse_question(question):
    if not question or not question.strip():
        return _unknown("empty")

    q = _clean(question)
    if not q:
        return _unknown("empty")

    if MEDICAL_ADVICE_PATTERN.search(q):
        return _unknown("medical")

    has_verb_have = re.search(r"\b(have|has|there|equipped|available)\b", q)
    asks_list = re.search(r"\b(what|which|list|show|tell|all)\b", q)

    # ---- emergency
    if re.search(r"\b(emergency|casualty)\b", q) and re.search(
            r"\b(available|have|has|provide|provides|offer|offers|service|services|open|24)\b", q):
        return _result("CHECK_EMERGENCY", {}, "emergency_ready", [HOSPITAL])

    # ---- timings
    timing_word = re.search(r"\b(timings?|timing|times?|hours|open|opens|close|closes|when|schedule)\b", q)
    # Check named hospital services before the generic doctor patterns below.
    # Otherwise, words such as "OPD", "visiting", or "pharmacy" can be
    # mistaken for a doctor's name in questions ending with "timings".
    if re.search(r"\bvisit(?:ing|ors?|s)?\b", q) and timing_word:
        return _result("FIND_VISITING_HOURS", {}, "visiting_hours", [HOSPITAL, "Hours"])
    if re.search(r"\b(opd|outpatient)\b", q) and timing_word:
        return _result("FIND_OPD_TIMING", {}, "opd_timing", [HOSPITAL, "Timing"])
    if re.search(r"\bpharmacy\b", q) and timing_word:
        return _result("FIND_PHARMACY_TIMING", {}, "pharmacy_timing", [HOSPITAL, "Timing"])
    if re.search(r"\b(lab|laboratory)\b", q) and timing_word:
        return _result("FIND_LAB_TIMING", {}, "lab_timing", [HOSPITAL, "Timing"])
    if timing_word and re.search(r"\b(hospital|citycare)\b", q):
        return _result("FIND_HOSPITAL_TIMING", {}, "hospital_open", [HOSPITAL, "Timing"])

    doctor_name = (
        _name_after(r"\b(?:when|what time) (?:is|does) (?:dr )?(\w+) (?:available|work)\b", q)
        or _name_after(r"\b(?:availability|timings?|timing|schedule|hours) (?:of|for) (?:dr )?(\w+)\b", q)
        or _name_after(r"\b(?:dr )?(\w+)(?: s)? (?:working )?(?:availability|timings?|timing|schedule|hours)\b", q)
    )
    if doctor_name:
        return _result("FIND_DOCTOR_AVAILABILITY", {"doctor": doctor_name},
                       "doctor_available", [doctor_name, "Timing"])
    if timing_word and re.search(r"\bdoctors?\b", q):
        return _result("LIST_DOCTOR_AVAILABILITY", {}, "doctor_available", ["Doctor", "Timing"])

    # ---- lists
    if re.search(r"\bfacilit(?:y|ies)\b", q) and asks_list:
        return _result("LIST_FACILITIES", {}, "available_facility", [HOSPITAL, "Facility"])
    if re.search(r"\bservices?\b", q) and asks_list:
        return _result("LIST_SERVICES", {}, "available_service", [HOSPITAL, "Service"])
    if re.search(r"\bdepartments?\b", q) and asks_list and not re.search(r"\b(doctors?|dr)\b", q) \
            and not re.search(r"\b(does|do|is)\b.*\b(work|specializ\w*|belong)\b", q):
        return _result("LIST_DEPARTMENTS", {}, "department", ["Department"])

    # ---- questions about ONE named doctor
    name = (_name_after(r"\bwhat (?:does|is) (?:dr )?(\w+) (?:specializ\w*|specialis\w*) in\b", q)
            or _name_after(r"\bspecializ\w* of (?:dr )?(\w+)", q))
    if name:
        return _result("FIND_SPECIALIZATION_OF_DOCTOR", {"doctor": name},
                       "specializes", [name, "Department"])
    name = _name_after(r"\b(?:which|what) department (?:does|is) (?:dr )?(\w+) (?:work|belong|in)", q)
    if name:
        return _result("FIND_DEPARTMENT_OF_DOCTOR", {"doctor": name}, "works_in", [name, "Department"])

    # ---- department / doctor questions
    dept_word, department = _find(DEPARTMENT_WORDS, q)
    if department is None:
        # unknown department word, e.g. "specializes in oncology" (maybe added by the admin later)
        match = re.search(r"\b(?:specializ\w*|specialis\w*|work\w*) (?:in|at)(?: the)? ([a-z ]+?)(?: department)?$", q)
        if match:
            department = match.group(1).strip().replace(" ", "_")
            dept_word = match.group(1)

    if department:
        entities = {"department": department}
        if re.match(r"^(does|do|is|are)\b", q) and re.search(r"\bdepartment\b", q) and has_verb_have \
                and not re.search(r"\b(doctors?|dr)\b", q):
            return _result("CHECK_DEPARTMENT", entities, "department", [department])
        if re.search(r"\bspecializ\w*|\bspecialis\w*|\bspeciali?ty\b", q):
            return _result("FIND_DOCTOR_BY_SPECIALIZATION", entities, "specializes", ["Doctor", department])
        if re.search(r"\b(work|works|working)\b", q) or (
                re.search(r"\bdepartment\b", q) and re.search(r"\b(doctors?|who)\b", q)):
            return _result("FIND_DOCTOR_BY_DEPARTMENT", entities, "works_in", ["Doctor", department])
        if dept_word in TITLE_WORDS:
            entities["title"] = dept_word
            return _result("FIND_DOCTOR_BY_TITLE", entities, "specializes", ["Doctor", department])
        if re.search(r"\b(doctors?|who|physicians?|specialists?)\b", q):
            return _result("FIND_DOCTOR_BY_SPECIALIZATION", entities, "specializes", ["Doctor", department])

    if re.search(r"\bdoctors\b", q) and asks_list:
        return _result("LIST_DOCTORS", {}, "doctor", ["Doctor"])

    # ---- does the hospital have / provide ...
    asks_provide = re.search(r"\b(provide|provides|offer|offers|service)\b", q)
    service_word, service = _find(SERVICE_WORDS, q)
    facility_word, facility = _find(FACILITY_WORDS, q)

    if re.match(r"^(does|do|is|are|can)\b", q) or has_verb_have:
        if service and (asks_provide or not facility):
            return _result("CHECK_SERVICE", {"service": service}, "available_service", [HOSPITAL, service])
        if facility:
            return _result("CHECK_FACILITY", {"facility": facility}, "available_facility", [HOSPITAL, facility])
        # unknown facility word, e.g. "does the hospital have a cafeteria" (admin may add it later)
        match = re.search(r"\b(?:have|has) (?:an? |any |the )?([a-z\- ]+?)(?: facility| facilities| available)?$", q)
        if match and len(match.group(1).split()) <= 3:
            thing = match.group(1).strip().replace("-", "_").replace(" ", "_")
            return _result("CHECK_FACILITY", {"facility": thing}, "available_facility", [HOSPITAL, thing])

    keyword_intent = _detect_keyword_intent(q, _dynamic_keyword_aliases())
    if keyword_intent is not None:
        return keyword_intent

    return _unknown()
