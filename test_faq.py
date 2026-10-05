"""Regression tests for FAQ paths that must be answered by pyDatalog queries."""

import unittest

import inference_engine as engine
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


if __name__ == "__main__":
    unittest.main()
