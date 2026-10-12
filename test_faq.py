"""Regression tests for FAQ paths that must be answered by pyDatalog queries."""

import os
import tempfile
import unittest
from unittest import mock

import inference_engine as engine
import knowledge_base as kb
import query_processor
import reasoning_trace


class HospitalFaqQueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine.load_knowledge_base()

    def assert_derived_answer(self, question, logical_query, answer_fragment, rule_name):
        result = reasoning_trace.answer_question(question)
        self.assertTrue(result["found"], result)
        self.assertEqual(result["logical_query"], logical_query)
        self.assertIn(answer_fragment, result["answer"])
        self.assertIn("Rule applied: {}".format(rule_name), result["trace"])

    def test_doctor_availability_timing_uses_derived_query(self):
        self.assert_derived_answer(
            "When is Dr. Arun available?",
            "doctor_available(arun, Timing)",
            "Monday - Saturday, 10:00 AM - 1:00 PM",
            "doctor_available(D, T) <= doctor(D) & doctor_availability(D, T)",
        )

    def test_doctor_availability_list_uses_derived_query(self):
        self.assert_derived_answer(
            "What are the doctor timings?",
            "doctor_available(Doctor, Timing)",
            "Dr. Priya: Monday - Friday, 11:00 AM - 3:00 PM",
            "doctor_available(D, T) <= doctor(D) & doctor_availability(D, T)",
        )

    def test_hospital_facility_uses_existing_derived_query(self):
        self.assert_derived_answer(
            "Does the hospital have an ICU?",
            "available_facility(citycare_hospital, icu)",
            "has an ICU.",
            "available_facility(H, F) <= has_facility(H, F) & facility(F)",
        )

    def test_hospital_service_uses_existing_derived_query(self):
        self.assert_derived_answer(
            "Does the hospital provide surgery?",
            "available_service(citycare_hospital, surgery)",
            "provides the Surgery service.",
            "available_service(H, S) <= provides(H, S) & service(S)",
        )

    def test_hospital_timing_uses_derived_query(self):
        self.assert_derived_answer(
            "What are the hospital timings?",
            "hospital_open(citycare_hospital, Timing)",
            "Daily, 8:00 AM - 8:00 PM",
            "hospital_open(H, T) <= hospital_timing(H, T)",
        )

    def test_new_timing_fact_validation_preserves_human_readable_value(self):
        parsed = query_processor.parse_question("When is Dr. Arun available?")
        self.assertEqual(parsed["query"], ("doctor_available", ["arun", "Timing"]))
        self.assertTrue(engine.holds(
            "doctor_availability", ["arun", "Monday - Saturday, 10:00 AM - 1:00 PM"]
        ))


class FolAndSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine.load_knowledge_base()

    def test_direct_fact_and_derived_rule_are_distinct(self):
        self.assertTrue(engine.holds("specializes", ["kumar", "orthopedics"]))
        self.assertEqual(engine.query("works_in", ["Doctor", "orthopedics"]), [{"Doctor": "kumar"}])
        direct_trace = reasoning_trace.answer_question("Which doctor specializes in cardiology?")["trace"]
        derived_trace = reasoning_trace.answer_question("Which doctor works in orthopedics?")["trace"]
        self.assertNotIn("Rule applied: works_in", direct_trace)
        self.assertIn("Rule applied: works_in(D, Dep) <= specializes(D, Dep)", derived_trace)
        self.assertIn("Knowledge base contains: specializes(kumar, orthopedics)", derived_trace)

        emergency_trace = reasoning_trace.answer_question("Is emergency service available?")["trace"]
        self.assertIn("Rule applied: emergency_ready(H) <= provides(H, 'emergency') & emergency_available(H, 'true')",
                      emergency_trace)
        self.assertIn("Knowledge base contains: provides(citycare_hospital, emergency)", emergency_trace)

    def test_empty_unknown_and_medical_questions_are_safe(self):
        self.assertEqual(reasoning_trace.answer_question("   ")["answer"], "Please type a question first.")
        self.assertEqual(reasoning_trace.answer_question("Where can I park?")["answer"], reasoning_trace.NO_ANSWER)
        medical = reasoning_trace.answer_question("What medicine should I take for chest pain?")
        self.assertEqual(medical["answer"], reasoning_trace.MEDICAL_REFUSAL)
        self.assertIsNone(medical["logical_query"])

    def test_unknown_entities_are_not_invented(self):
        self.assertFalse(reasoning_trace.answer_question("When is Dr. Zephyr available?")["found"])
        self.assertFalse(reasoning_trace.answer_question("Which doctor specializes in oncology?")["found"])
        self.assertFalse(reasoning_trace.answer_question("Does the hospital have a cafeteria?")["found"])

    def test_logical_query_validation_rejects_bad_admin_queries(self):
        for text in ("", "specializes()", "specializes(Doctor, )", "Specializes(Doctor, cardiology)",
                     "specializes(Doctor, 'cardiology)"):
            with self.subTest(text=text):
                with self.assertRaises(engine.InferenceError):
                    engine.parse_logical_query(text)

    def test_repeated_list_queries_are_stable_and_unique(self):
        first = engine.query("available_facility", ["citycare_hospital", "Facility"])
        second = engine.query("available_facility", ["citycare_hospital", "Facility"])
        values = [row["Facility"] for row in first]
        self.assertEqual(first, second)
        self.assertEqual(len(values), len(set(values)))


class PersistenceAndAdminTests(unittest.TestCase):
    """Exercise admin CRUD helpers against a temporary JSON file only."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_path, self.original_dir = kb.KB_PATH, kb.BASE_DIR
        kb.KB_PATH = os.path.join(self.temp_dir.name, "knowledge_base.json")
        kb.BASE_DIR = self.temp_dir.name
        self.facts = [
            {"predicate": "department", "args": ["cardiology"]},
            {"predicate": "department", "args": ["neurology"]},
            {"predicate": "doctor", "args": ["arun"]},
            {"predicate": "doctor", "args": ["ravi"]},
            {"predicate": "specializes", "args": ["arun", "cardiology"]},
            {"predicate": "doctor_availability", "args": ["arun", "Monday, 9 AM - 1 PM"]},
        ]
        kb.save_facts(self.facts, engine.derived_predicates())
        engine.load_knowledge_base()

    def tearDown(self):
        kb.KB_PATH, kb.BASE_DIR = self.original_path, self.original_dir
        self.temp_dir.cleanup()
        engine.load_knowledge_base()

    def test_admin_crud_save_reload_and_backup(self):
        facts = kb.load_facts()
        facts = kb.add_fact(facts, "specializes", ["ravi", "cardiology"], engine.derived_predicates())
        kb.save_facts(facts, engine.derived_predicates())
        engine.load_knowledge_base()
        self.assertEqual(engine.query("specializes", ["Doctor", "cardiology"]),
                         [{"Doctor": "arun"}, {"Doctor": "ravi"}])

        ravi_index = next(i for i, fact in enumerate(facts)
                          if fact == {"predicate": "specializes", "args": ["ravi", "cardiology"]})
        facts = kb.update_fact(facts, ravi_index, "specializes", ["ravi", "neurology"],
                               engine.derived_predicates())
        kb.save_facts(facts, engine.derived_predicates())
        engine.load_knowledge_base()
        self.assertEqual(engine.query("specializes", ["Doctor", "cardiology"]), [{"Doctor": "arun"}])
        self.assertEqual(engine.query("specializes", ["Doctor", "neurology"]), [{"Doctor": "ravi"}])

        facts = kb.delete_fact(facts, ravi_index)
        kb.save_facts(facts, engine.derived_predicates())
        engine.load_knowledge_base()
        self.assertEqual(engine.query("specializes", ["Doctor", "neurology"]), [])
        self.assertEqual(kb.load_facts(), facts)  # persisted and reloaded

        backup_path = kb.backup_kb()
        self.assertTrue(os.path.exists(backup_path))
        with open(kb.KB_PATH, encoding="utf-8") as source, open(backup_path, encoding="utf-8") as backup:
            self.assertEqual(backup.read(), source.read())

    def test_validation_rejects_bad_and_duplicate_updates(self):
        with self.assertRaises(kb.FactError):
            kb.add_fact(self.facts, "specializes", ["arun", "cardiology"], engine.derived_predicates())
        with self.assertRaises(kb.FactError):
            kb.add_fact(self.facts, "works_in", ["arun", "cardiology"], engine.derived_predicates())
        with self.assertRaises(kb.FactError):
            kb.add_fact(self.facts, "bad-name", ["x"], engine.derived_predicates())
        with self.assertRaises(kb.FactError):
            kb.add_fact(self.facts, "specializes", ["arun", ""], engine.derived_predicates())
        with self.assertRaises(kb.KnowledgeBaseError):
            kb.save_facts([{"predicate": "doctor", "args": ["arun"]},
                           {"predicate": "doctor", "args": ["arun"]}])

    def test_failed_save_keeps_previous_file_and_cleans_temp_file(self):
        with open(kb.KB_PATH, encoding="utf-8") as file:
            before = file.read()
        changed = kb.add_fact(self.facts, "doctor", ["priya"], engine.derived_predicates())
        with mock.patch.object(kb.os, "replace", side_effect=OSError("simulated write failure")):
            with self.assertRaises(kb.KnowledgeBaseError):
                kb.save_facts(changed, engine.derived_predicates())
        with open(kb.KB_PATH, encoding="utf-8") as file:
            self.assertEqual(file.read(), before)
        self.assertFalse(os.path.exists(kb.KB_PATH + ".tmp"))

    def test_missing_invalid_and_empty_knowledge_bases_are_handled(self):
        os.remove(kb.KB_PATH)
        with self.assertRaises(kb.KnowledgeBaseError):
            kb.load_facts()
        with self.assertRaises(kb.KnowledgeBaseError):
            kb.backup_kb()

        with open(kb.KB_PATH, "w", encoding="utf-8") as file:
            file.write("{ not valid json")
        with self.assertRaises(kb.KnowledgeBaseError):
            kb.load_facts()

        kb.save_facts([], engine.derived_predicates())
        self.assertEqual(engine.load_knowledge_base(), 0)
        self.assertEqual(engine.query("department", ["Department"]), [])


DOCUMENTED_QUERY_CASES = (
    ("doctor_cardiology", "Which doctor specializes in cardiology?", "specializes(Doctor, cardiology)", "Dr. Arun"),
    ("neurologist", "Who is the neurologist?", "specializes(Doctor, neurology)", "Dr. Priya"),
    ("doctor_orthopedics", "Which doctor works in orthopedics?", "works_in(Doctor, orthopedics)", "Dr. Kumar"),
    ("doctors_cardiology", "Which doctors specialize in cardiology?", "specializes(Doctor, cardiology)", "Dr. Arun"),
    ("kumar_available_timing", "What is the available timing for Dr. Kumar?", "doctor_available(kumar, Timing)", "2:00 PM - 6:00 PM"),
    ("kumar_working_hours", "What are Dr. Kumar's working hours?", "doctor_available(kumar, Timing)", "2:00 PM - 6:00 PM"),
    ("kumar_available_when", "When is Dr. Kumar available?", "doctor_available(kumar, Timing)", "2:00 PM - 6:00 PM"),
    ("facility_mri", "Does the hospital have an MRI?", "available_facility(citycare_hospital, mri)", "has an MRI"),
    ("facility_blood_bank", "Does the hospital have a blood bank?", "available_facility(citycare_hospital, blood_bank)", "has a blood bank"),
    ("facility_laboratory", "Does the hospital have a laboratory?", "available_facility(citycare_hospital, laboratory)", "has a laboratory"),
    ("facility_list", "What facilities are available?", "available_facility(citycare_hospital, Facility)", "- MRI"),
    ("facility_ct_scan", "Does CityCare Hospital have a CT scan?", "available_facility(citycare_hospital, ct_scan)", "CT scan"),
    ("facility_xray", "Does the hospital have an X-ray facility?", "available_facility(citycare_hospital, xray)", "X-ray"),
    ("service_list", "What services does the hospital provide?", "available_service(citycare_hospital, Service)", "- Emergency"),
    ("service_emergency", "Does the hospital provide emergency services?", "emergency_ready(citycare_hospital)", "emergency service is available"),
    ("service_radiology", "Does the hospital provide radiology services?", "available_service(citycare_hospital, radiology)", "Radiology service"),
    ("service_opd", "Does the hospital provide OPD services?", "available_service(citycare_hospital, opd)", "OPD service"),
    ("timing_opd", "What are the OPD timings?", "opd_timing(citycare_hospital, Timing)", "9:00 AM - 5:00 PM"),
    ("timing_visiting", "When are visiting hours?", "visiting_hours(citycare_hospital, Hours)", "4:00 PM - 7:00 PM"),
    ("timing_pharmacy", "What are the pharmacy timings?", "pharmacy_timing(citycare_hospital, Timing)", "8:00 AM - 10:00 PM"),
    ("timing_laboratory", "What are the laboratory timings?", "lab_timing(citycare_hospital, Timing)", "7:00 AM - 8:00 PM"),
    ("emergency_available", "Is emergency service available?", "emergency_ready(citycare_hospital)", "emergency service is available"),
    # Additional sample and live-demo questions documented in README.md.
    ("facility_icu", "Does the hospital have an ICU?", "available_facility(citycare_hospital, icu)", "has an ICU"),
    ("service_surgery", "Does the hospital provide surgery?", "available_service(citycare_hospital, surgery)", "Surgery service"),
    ("doctor_timing_list", "What are the doctor timings?", "doctor_available(Doctor, Timing)", "Dr. Arun:"),
    ("timing_hospital", "What are the hospital timings?", "hospital_open(citycare_hospital, Timing)", "Daily, 8:00 AM - 8:00 PM"),
    ("arun_specialization", "What does Dr. Arun specialize in?", "specializes(arun, Department)", "Cardiology"),
    ("department_cardiology", "Does the hospital have a cardiology department?", "department(cardiology)", "Cardiology department"),
    ("doctor_works_cardiology", "Which doctor works in cardiology?", "works_in(Doctor, cardiology)", "Dr. Arun"),
    ("department_list", "What departments are available?", "department(Department)", "- Cardiology"),
    ("doctor_list", "What doctors are available?", "doctor(Doctor)", "- Dr. Arun"),
)


def _documented_case(question, expected_query, expected_answer):
    def test(self):
        engine.load_knowledge_base()
        result = reasoning_trace.answer_question(question)
        self.assertTrue(result["found"], result)
        self.assertEqual(result["logical_query"], expected_query)
        self.assertIn(expected_answer, result["answer"])
    return test


class DocumentedHospitalRegressionTests(unittest.TestCase):
    """Every hospital-domain query listed in the pre-demo audit request."""


for _name, _question, _query, _answer in DOCUMENTED_QUERY_CASES:
    setattr(DocumentedHospitalRegressionTests, "test_" + _name,
            _documented_case(_question, _query, _answer))


if __name__ == "__main__":
    unittest.main()
