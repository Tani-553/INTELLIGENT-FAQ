"""
reasoning_trace.py
------------------
Builds the final answer text and the REASONING TRACE.

The trace is not canned text: every "knowledge base contains ..." line is
confirmed by asking the inference engine whether that exact fact/rule
condition really holds. If a fact is deleted, the trace changes with it.

answer_question() is the one function the GUI calls. It runs the whole flow:
    question -> query processor -> inference engine -> trace -> formatted answer
"""

import inference_engine as engine
import query_processor

NO_ANSWER = "Sorry, I could not derive an answer from the current hospital knowledge base."
NO_TRACE = "No matching fact or rule was found."
MEDICAL_REFUSAL = ("This system provides hospital information and FAQs only.\n"
                   "It cannot provide diagnosis or treatment advice.")

# ---------------------------------------------------------------- display names

PRETTY = {"mri": "MRI", "ct_scan": "CT Scan", "xray": "X-ray", "ent": "ENT",
          "opd": "OPD", "icu": "ICU", "citycare_hospital": "CityCare Hospital"}

FACILITY_PHRASE = {"mri": "an MRI facility", "ct_scan": "a CT scan facility",
                   "xray": "an X-ray facility", "laboratory": "a laboratory",
                   "pharmacy": "a pharmacy", "blood_bank": "a blood bank",
                   "icu": "an ICU", "ambulance": "an ambulance"}


def pretty(constant):
    return PRETTY.get(constant, constant.replace("_", " ").title())


def doctor_name(constant):
    return "Dr. " + pretty(constant)


def with_article(text):
    return ("an " if text[:1].lower() in "aeiou" else "a ") + text


# ---------------------------------------------------------------- answer text

def format_answer(parsed, answers):
    """Turn the inference result into a readable sentence. Only uses what was derived."""
    if not answers:
        return NO_ANSWER

    intent, ent = parsed["intent"], parsed["entities"]
    hospital = pretty(query_processor.HOSPITAL)

    def values(variable):
        return [row[variable] for row in answers]

    if intent in ("FIND_DOCTOR_BY_SPECIALIZATION", "FIND_DOCTOR_BY_TITLE"):
        verb, dept = "specializes in", pretty(ent["department"])
        plural = "Doctors who specialize in"
    elif intent == "FIND_DOCTOR_BY_DEPARTMENT":
        verb, dept = "works in", pretty(ent["department"])
        plural = "Doctors who work in"
    else:
        verb = dept = plural = None

    if verb:
        doctors = [doctor_name(d) for d in values("Doctor")]
        if len(doctors) == 1:
            return "{} {} {}.".format(doctors[0], verb, dept)
        return "{} {}:\n{}".format(plural, dept, "\n".join(doctors))

    if intent == "FIND_SPECIALIZATION_OF_DOCTOR":
        return "{} specializes in {}.".format(doctor_name(ent["doctor"]),
                                              ", ".join(pretty(d) for d in values("Department")))
    if intent == "FIND_DEPARTMENT_OF_DOCTOR":
        return "{} works in {}.".format(doctor_name(ent["doctor"]),
                                        ", ".join(pretty(d) for d in values("Department")))
    if intent == "FIND_DOCTOR_AVAILABILITY":
        return "{} is available {}.".format(doctor_name(ent["doctor"]),
                                              "; ".join(values("Timing")))
    if intent == "CHECK_FACILITY":
        phrase = FACILITY_PHRASE.get(ent["facility"], with_article(pretty(ent["facility"]).lower() + " facility"))
        return "Yes, {} has {}.".format(hospital, phrase)
    if intent == "CHECK_SERVICE":
        return "Yes, {} provides the {} service.".format(hospital, pretty(ent["service"]))
    if intent == "CHECK_DEPARTMENT":
        return "Yes, {} has {} department.".format(hospital, with_article(pretty(ent["department"])))
    if intent == "CHECK_EMERGENCY":
        return "Yes, emergency service is available."
    if intent == "LIST_FACILITIES":
        return "Facilities available at {}:\n{}".format(hospital, "\n".join("- " + pretty(f) for f in values("Facility")))
    if intent == "LIST_SERVICES":
        return "Services provided by {}:\n{}".format(hospital, "\n".join("- " + pretty(s) for s in values("Service")))
    if intent == "LIST_DEPARTMENTS":
        return "Departments at {}:\n{}".format(hospital, "\n".join("- " + pretty(d) for d in values("Department")))
    if intent == "LIST_DOCTORS":
        return "Doctors at {}:\n{}".format(hospital, "\n".join("- " + doctor_name(d) for d in values("Doctor")))
    if intent == "LIST_DOCTOR_AVAILABILITY":
        return "Doctor availability:\n{}".format(
            "\n".join("- {}: {}".format(doctor_name(row["Doctor"]), row["Timing"])
                      for row in answers))

    timing_text = {"FIND_OPD_TIMING": ("OPD timings are", "Timing"),
                   "FIND_VISITING_HOURS": ("Visiting hours are", "Hours"),
                   "FIND_PHARMACY_TIMING": ("Pharmacy timings are", "Timing"),
                   "FIND_LAB_TIMING": ("Laboratory timings are", "Timing"),
                   "FIND_HOSPITAL_TIMING": ("Hospital timings are", "Timing")}
    if intent in timing_text:
        label, variable = timing_text[intent]
        return "{} {}.".format(label, "; ".join(values(variable)))
    return NO_ANSWER


# ---------------------------------------------------------------- reasoning trace

def _atom_text(predicate, args):
    return engine.format_query(predicate, args)


def _proof_lines(predicate, args, indent):
    """
    Explain why one fully-instantiated atom is true, e.g. works_in(kumar, orthopedics).
    Base facts are confirmed against the engine; rule-derived atoms show the rule and
    check every condition in the rule body.
    """
    pad = "   " * indent
    atom = _atom_text(predicate, args)
    rule = engine.RULE_INFO.get(predicate)
    if rule is None:
        return ["{}Knowledge base contains: {}".format(pad, atom)]

    mapping = dict(zip(rule["head"][1], args))
    lines = ["{}Rule applied: {}".format(pad, rule["text"]),
             "{}   ({})".format(pad, rule["meaning"])]
    for body_pred, body_args in rule["body"]:
        instance = [mapping.get(t, t) for t in body_args]
        if engine.holds(body_pred, instance):
            lines += _proof_lines(body_pred, instance, indent + 1)
        else:
            lines.append("{}   Condition NOT satisfied: {}".format(pad, _atom_text(body_pred, instance)))
    return lines


def _why_no_answer_lines(predicate, args):
    """For a failed query, show what was looked for (and which rule conditions had no match)."""
    rule = engine.RULE_INFO.get(predicate)
    if rule is None:
        return ["No fact matching {} exists in the knowledge base.".format(_atom_text(predicate, args))]
    mapping = dict(zip(rule["head"][1], args))
    lines = ["'{}' is derived by the rule:".format(predicate), "   " + rule["text"],
             "Checking the conditions of the rule:"]
    for body_pred, body_args in rule["body"]:
        instance = [mapping.get(t, t) for t in body_args]
        found = engine.query(body_pred, instance)
        lines.append("   {} -> {}".format(_atom_text(body_pred, instance),
                                          "match found" if found else "no match"))
    return lines


def _numbered(steps):
    """steps = list of line-lists; produce '1. ...' numbered paragraphs."""
    out = []
    for number, step_lines in enumerate(steps, start=1):
        out.append("{}. {}".format(number, step_lines[0]))
        out += ["   " + line for line in step_lines[1:]]
        out.append("")
    return "\n".join(out).rstrip()


def build_trace(parsed, answers, answer_text):
    predicate, args = parsed["query"]
    entity_text = ", ".join("{} = {}".format(k, v) for k, v in parsed["entities"].items())
    step1 = ["Query interpreted as:", "   " + _atom_text(predicate, args),
             "   (intent = {}{})".format(parsed["intent"], ", " + entity_text if entity_text else "")]
    steps = [step1]

    if not answers:
        steps.append(["pyDatalog inference engine evaluated the query: no answer derived."]
                     + ["   " + l for l in _why_no_answer_lines(predicate, args)])
        steps.append([NO_TRACE])
        return _numbered(steps)

    if predicate in engine.RULE_INFO:
        steps.append(["'{}' is a derived predicate (defined by a rule, not stored directly).".format(predicate)])
    steps.append(["pyDatalog inference engine evaluated the query and derived {} answer(s).".format(len(answers))])

    for number, row in enumerate(answers, start=1):
        bound = [row.get(a, a) for a in args]              # fill variables with the derived values
        binding_text = ", ".join("{} = {}".format(k, v) for k, v in row.items())
        header = "Answer {}: {}".format(number, binding_text) if binding_text else "Query is true:"
        steps.append([header] + _proof_lines(predicate, bound, 0))

    steps.append(["Therefore:"] + ["   " + line for line in answer_text.split("\n")])
    return _numbered(steps)


# ---------------------------------------------------------------- the whole pipeline

def answer_question(question):
    """
    Full flow used by the GUI. Never raises: always returns a dictionary
        {"answer": str, "trace": str, "logical_query": str or None, "found": bool}
    """
    try:
        parsed = query_processor.parse_question(question)

        if parsed["status"] == "empty":
            return {"answer": "Please type a question first.", "trace": "", "logical_query": None, "found": False}
        if parsed["status"] == "medical":
            return {"answer": MEDICAL_REFUSAL, "logical_query": None, "found": False,
                    "trace": "1. The question asks for medical advice.\n"
                             "2. No logical query was generated (this system only answers hospital information questions)."}
        if parsed["status"] == "unknown":
            return {"answer": NO_ANSWER, "logical_query": None, "found": False,
                    "trace": "1. The question did not match any supported question pattern,\n"
                             "   so no logical query could be built.\n\n2. " + NO_TRACE}

        predicate, args = parsed["query"]
        answers = engine.query(predicate, args)          # <-- the actual logical inference
        answer_text = format_answer(parsed, answers)
        return {"answer": answer_text, "trace": build_trace(parsed, answers, answer_text),
                "logical_query": _atom_text(predicate, args), "found": bool(answers)}

    except engine.InferenceError as err:
        return {"answer": "Sorry, something went wrong during inference.",
                "trace": str(err), "logical_query": None, "found": False}
    except Exception as err:                              # the GUI must never crash
        return {"answer": "Sorry, an unexpected error occurred.",
                "trace": "{}: {}".format(type(err).__name__, err), "logical_query": None, "found": False}
