"""
inference_engine.py
-------------------
The First-Order Logic part of the project, built on pyDatalog.

* Facts  are loaded from knowledge_base.json  (via knowledge_base.py).
* Rules  are written below, in RULES_TEXT.
* Queries are answered by pyDatalog's resolution engine, NOT by searching the JSON.

Convention used everywhere in this project:
    Arguments starting with a CAPITAL letter are variables  (Doctor, Department)
    Anything else is a constant                             (arun, cardiology)
"""

import re
from pyDatalog import pyDatalog

import knowledge_base as kb


class InferenceError(Exception):
    """The logical query could not be parsed or evaluated."""


# ---------------------------------------------------------------- RULES
# These are the pyDatalog rules ("<=" means "if").
RULES_TEXT = """
works_in(D, Dep) <= specializes(D, Dep)
available_facility(H, F) <= has_facility(H, F) & facility(F)
available_service(H, S) <= provides(H, S) & service(S)
doctor_available(D, T) <= doctor(D) & doctor_availability(D, T)
hospital_open(H, T) <= hospital_timing(H, T)
emergency_ready(H) <= provides(H, 'emergency') & emergency_available(H, 'true')
"""

# The same rules in a structured form. The reasoning trace uses this table to
# show which rule fired and which facts it needed (variables are capital letters).
RULE_INFO = {
    "works_in": {
        "head": ("works_in", ["D", "Dep"]),
        "body": [("specializes", ["D", "Dep"])],
        "text": "works_in(D, Dep) <= specializes(D, Dep)",
        "meaning": "If a doctor specializes in a department, the doctor works in that department.",
    },
    "available_facility": {
        "head": ("available_facility", ["H", "F"]),
        "body": [("has_facility", ["H", "F"]), ("facility", ["F"])],
        "text": "available_facility(H, F) <= has_facility(H, F) & facility(F)",
        "meaning": "A facility is available if the hospital has it and it is a known facility.",
    },
    "available_service": {
        "head": ("available_service", ["H", "S"]),
        "body": [("provides", ["H", "S"]), ("service", ["S"])],
        "text": "available_service(H, S) <= provides(H, S) & service(S)",
        "meaning": "A service is available if the hospital provides it and it is a known service.",
    },
    "doctor_available": {
        "head": ("doctor_available", ["D", "T"]),
        "body": [("doctor", ["D"]), ("doctor_availability", ["D", "T"])],
        "text": "doctor_available(D, T) <= doctor(D) & doctor_availability(D, T)",
        "meaning": "A doctor's availability is shown when the person is a known doctor and has a recorded schedule.",
    },
    "hospital_open": {
        "head": ("hospital_open", ["H", "T"]),
        "body": [("hospital_timing", ["H", "T"])],
        "text": "hospital_open(H, T) <= hospital_timing(H, T)",
        "meaning": "Hospital opening hours are derived from the recorded hospital timing.",
    },
    "emergency_ready": {
        "head": ("emergency_ready", ["H"]),
        "body": [("provides", ["H", "emergency"]), ("emergency_available", ["H", "true"])],
        "text": "emergency_ready(H) <= provides(H, 'emergency') & emergency_available(H, 'true')",
        "meaning": "Emergency service is ready if the hospital provides it and it is marked available.",
    },
}


def derived_predicates():
    """Names of predicates that are defined by rules (they cannot be stored as facts)."""
    return set(RULE_INFO)


def is_variable(term):
    """Return True only for a pyDatalog-style variable identifier.

    Free-text facts such as ``Monday - Saturday, 10:00 AM - 1:00 PM`` may
    begin with a capital letter, but are constants rather than variables.
    """
    return bool(re.match(r"^[A-Z_][A-Za-z0-9_]*$", term))


# ---------------------------------------------------------------- loading

def load_knowledge_base():
    """
    (Re)load all facts from knowledge_base.json into pyDatalog and define the rules.
    Call this again after every change to the knowledge base.
    Returns the number of facts loaded.
    """
    # Validate before clearing pyDatalog so a malformed file cannot replace a
    # previously working in-memory knowledge base with a partial one.
    facts = kb.validate_facts(kb.load_facts(), derived_predicates())
    pyDatalog.clear()
    for fact in facts:
        pyDatalog.assert_fact(fact["predicate"], *fact["args"])
    pyDatalog.load(RULES_TEXT)
    return len(facts)


# ---------------------------------------------------------------- querying

def format_query(predicate, args):
    """('specializes', ['Doctor', 'cardiology']) -> 'specializes(Doctor, cardiology)'"""
    return "{}({})".format(predicate, ", ".join(args))


def _to_pydatalog_text(predicate, args):
    """Variables stay as they are, constants are quoted so pyDatalog treats them as values."""
    parts = [a if is_variable(a) else "'{}'".format(a) for a in args]
    return "{}({})".format(predicate, ", ".join(parts))


def query(predicate, args):
    """
    Ask pyDatalog a logical query.

    Returns a list of answers. Each answer is a dictionary {variable: value}.
    * query with variables  -> e.g. [{"Doctor": "arun"}, {"Doctor": "ravi"}]
    * query with no variables -> [{}] if it is true, [] if it is not
    * nothing derivable     -> []
    """
    variables = []
    for a in args:
        if is_variable(a) and a not in variables:
            variables.append(a)
    try:
        result = pyDatalog.ask(_to_pydatalog_text(predicate, args))
    except AttributeError as err:
        if "without definition" in str(err):      # no fact or rule for this predicate at all
            return []
        raise InferenceError("Inference error: {}".format(err))
    except Exception as err:
        raise InferenceError("Inference error: {}".format(err))

    if result is None:
        return []
    answers = [dict(zip(variables, row)) for row in result.answers]
    return sorted(answers, key=lambda row: [str(v) for v in row.values()])


def holds(predicate, args):
    """True if the fully-constant atom can be derived."""
    return len(query(predicate, args)) > 0


def parse_logical_query(text):
    """
    Turn text typed by the administrator, e.g.  specializes(Doctor, cardiology)
    into ('specializes', ['Doctor', 'cardiology']).
    """
    match = re.match(r"^\s*([a-z][a-z0-9_]*)\s*\((.*)\)\s*$", text or "", re.DOTALL)
    if not match:
        raise InferenceError("Query must look like  predicate(Arg1, Arg2)  "
                             "- for example  specializes(Doctor, cardiology)")
    predicate, inner = match.group(1), match.group(2)

    args, current, quote = [], "", None
    for ch in inner:                              # split on commas that are not inside quotes
        if quote:
            if ch == quote:
                quote = None
            else:
                current += ch
        elif ch in "'\"":
            quote = ch
        elif ch == ",":
            args.append(current.strip())
            current = ""
        else:
            current += ch
    args.append(current.strip())

    if quote or any(a == "" for a in args):
        raise InferenceError("Query has an empty argument or an unclosed quote.")
    return predicate, args
