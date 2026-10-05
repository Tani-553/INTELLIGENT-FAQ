"""
knowledge_base.py
-----------------
Everything that touches knowledge_base.json lives here:
loading, saving, validating, adding / editing / deleting facts, and backups.

A fact is stored as a small dictionary:
    {"predicate": "specializes", "args": ["arun", "cardiology"]}
which is the First-Order Logic fact  specializes(arun, cardiology).
"""

import json
import os
import re
import shutil
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KB_PATH = os.path.join(BASE_DIR, "knowledge_base.json")
HOSPITAL_NAME = "CityCare Hospital"

# How many arguments each known predicate needs.
# Predicates that are not listed here only need at least one argument.
EXPECTED_ARITY = {
    "department": 1, "doctor": 1, "facility": 1, "service": 1,
    "specializes": 2, "has_facility": 2, "provides": 2,
    "opd_timing": 2, "visiting_hours": 2, "pharmacy_timing": 2,
    "lab_timing": 2, "doctor_availability": 2, "hospital_timing": 2,
    "emergency_available": 2,
}

# For these predicates the last argument is free text (e.g. "9:00 AM - 5:00 PM"),
# so we keep its capital letters and spaces.
TEXT_VALUE_PREDICATES = {
    "opd_timing", "visiting_hours", "pharmacy_timing", "lab_timing",
    "doctor_availability", "hospital_timing",
}

NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class KnowledgeBaseError(Exception):
    """Problem with the knowledge base file (missing, broken JSON, bad structure)."""


class FactError(Exception):
    """A fact entered by the administrator is invalid."""


# ---------------------------------------------------------------- reading / writing

def fact_to_text(fact):
    """{"predicate": "specializes", "args": ["arun", "cardiology"]} -> 'specializes(arun, cardiology)'"""
    return "{}({})".format(fact["predicate"], ", ".join(fact["args"]))


def load_facts():
    """Read knowledge_base.json and return a list of fact dictionaries."""
    if not os.path.exists(KB_PATH):
        raise KnowledgeBaseError(
            "Knowledge base file not found:\n{}".format(KB_PATH))
    try:
        with open(KB_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as err:
        raise KnowledgeBaseError(
            "knowledge_base.json is not valid JSON (line {}, column {}): {}".format(
                err.lineno, err.colno, err.msg))
    except OSError as err:
        raise KnowledgeBaseError("Could not read knowledge base: {}".format(err))

    if not isinstance(data, dict) or not isinstance(data.get("facts"), list):
        raise KnowledgeBaseError('knowledge_base.json must contain a "facts" list.')

    facts = []
    for number, item in enumerate(data["facts"], start=1):
        if (not isinstance(item, dict) or not isinstance(item.get("predicate"), str)
                or not isinstance(item.get("args"), list) or not item["args"]):
            raise KnowledgeBaseError(
                'Fact number {} is malformed. Expected {{"predicate": "...", "args": [...]}}.'.format(number))
        args = []
        for value in item["args"]:
            if isinstance(value, bool):          # JSON true/false -> "true"/"false"
                value = "true" if value else "false"
            args.append(str(value))
        facts.append({"predicate": item["predicate"], "args": args})
    return facts


def save_facts(facts):
    """Write the facts to knowledge_base.json (one fact per line, easy to read)."""
    lines = [json.dumps(fact, ensure_ascii=False) for fact in facts]
    body = ",\n    ".join(lines)
    text = '{\n  "hospital": "%s",\n  "facts": [\n    %s\n  ]\n}\n' % (HOSPITAL_NAME, body)
    json.loads(text)                              # make sure we never write broken JSON
    temp_path = KB_PATH + ".tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(temp_path, KB_PATH)            # replace only after a complete write
    except OSError as err:
        raise KnowledgeBaseError("Could not save knowledge base: {}".format(err))


def backup_kb():
    """Copy knowledge_base.json to knowledge_base_backup_YYYYMMDD_HHMMSS.json."""
    if not os.path.exists(KB_PATH):
        raise KnowledgeBaseError("Nothing to back up: knowledge_base.json is missing.")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = os.path.join(BASE_DIR, "knowledge_base_backup_{}.json".format(stamp))
    counter = 1
    while os.path.exists(target):                 # never overwrite an earlier backup
        target = os.path.join(BASE_DIR, "knowledge_base_backup_{}_{}.json".format(stamp, counter))
        counter += 1
    try:
        shutil.copyfile(KB_PATH, target)
    except OSError as err:
        raise KnowledgeBaseError("Backup failed: {}".format(err))
    return target


# ---------------------------------------------------------------- validation

def validate_fact(predicate, args, facts, reserved=(), ignore_index=None):
    """
    Check a fact before it is saved. Returns the cleaned (predicate, args)
    or raises FactError with a friendly message.

    reserved     - predicate names defined by rules (cannot be stored as facts)
    ignore_index - index of the fact being edited (so it does not count as its own duplicate)
    """
    predicate = (predicate or "").strip().lower()
    if not predicate:
        raise FactError("Predicate must not be empty.")
    if not NAME_PATTERN.match(predicate):
        raise FactError("Predicate '{}' is invalid. Use lowercase letters, digits and underscores "
                        "(for example: specializes).".format(predicate))
    if predicate in reserved:
        raise FactError("'{}' is derived by a rule, so it cannot be added as a fact. "
                        "Add the base facts it depends on instead.".format(predicate))

    # remove empty trailing arguments (e.g. Argument 2 left blank for department(x))
    args = [str(a).strip() for a in args]
    while args and not args[-1]:
        args.pop()
    if not args:
        raise FactError("At least one argument is required.")
    if any(not a for a in args):
        raise FactError("An argument in the middle is empty. Fill it in or leave the later ones blank.")

    expected = EXPECTED_ARITY.get(predicate)
    if expected is not None and len(args) != expected:
        raise FactError("'{}' needs exactly {} argument(s) but {} were given.".format(
            predicate, expected, len(args)))

    cleaned = []
    for position, value in enumerate(args):
        if "'" in value or '"' in value:
            raise FactError("Quotes are not allowed in arguments: {}".format(value))
        is_free_text = predicate in TEXT_VALUE_PREDICATES and position == len(args) - 1
        if not is_free_text:
            value = re.sub(r"\s+", "_", value.lower())   # "Blood Bank" -> "blood_bank"
        cleaned.append(value)

    for index, existing in enumerate(facts):
        if index != ignore_index and existing["predicate"] == predicate and existing["args"] == cleaned:
            raise FactError("This fact already exists: {}".format(fact_to_text(existing)))
    return predicate, cleaned


# ---------------------------------------------------------------- add / edit / delete
# Each function returns a NEW list; the caller saves it with save_facts().

def add_fact(facts, predicate, args, reserved=()):
    predicate, args = validate_fact(predicate, args, facts, reserved)
    return facts + [{"predicate": predicate, "args": args}]


def update_fact(facts, index, predicate, args, reserved=()):
    if not 0 <= index < len(facts):
        raise FactError("Select a fact first.")
    predicate, args = validate_fact(predicate, args, facts, reserved, ignore_index=index)
    updated = list(facts)
    updated[index] = {"predicate": predicate, "args": args}
    return updated


def delete_fact(facts, index):
    if not 0 <= index < len(facts):
        raise FactError("Select a fact first.")
    return facts[:index] + facts[index + 1:]
