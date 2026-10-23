"""Regression tests for the Flask adapter around the existing FOL engine."""
import os
import tempfile
import unittest

import app
import auth
import inference_engine as engine
import knowledge_base as kb


class WebApplicationTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_path, self.old_dir = kb.KB_PATH, kb.BASE_DIR
        kb.KB_PATH, kb.BASE_DIR = os.path.join(self.temp_dir.name, "knowledge_base.json"), self.temp_dir.name
        kb.save_facts([
            {"predicate": "department", "args": ["cardiology"]},
            {"predicate": "doctor", "args": ["arun"]},
            {"predicate": "specializes", "args": ["arun", "cardiology"]},
            {"predicate": "facility", "args": ["mri"]},
            {"predicate": "has_facility", "args": ["citycare_hospital", "mri"]},
        ], engine.derived_predicates())
        engine.load_knowledge_base()

    def tearDown(self):
        kb.KB_PATH, kb.BASE_DIR = self.old_path, self.old_dir
        self.temp_dir.cleanup()
        engine.load_knowledge_base()

    def csrf(self):
        with self.client.session_transaction() as session:
            return session["csrf_token"]

    def login(self):
        self.client.get("/admin")
        return self.client.post("/admin", data={"username": app.ADMIN_USERNAME,
                                                  "password": app.ADMIN_PASSWORD,
                                                  "csrf_token": self.csrf()}, follow_redirects=False)

    def test_pages_and_dashboard_metrics_use_real_kb(self):
        for path in ("/", "/faq", "/doctors", "/departments", "/services", "/reasoning", "/analytics", "/about"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        stats = self.client.get("/api/dashboard").get_json()
        self.assertEqual(stats["facts"], 5)
        self.assertEqual(stats["doctors"], 1)
        self.assertEqual(stats["facilities"], 1)

    def test_faq_api_delegates_to_reasoning_engine(self):
        response = self.client.post("/api/faq", json={"question": "Which doctor specializes in cardiology?"})
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["found"])
        self.assertEqual(payload["logical_query"], "specializes(Doctor, cardiology)")
        self.assertIn("Dr. Arun", payload["answer"])
        self.assertEqual(self.client.post("/api/faq", json={"question": "x" * 1001}).status_code, 400)

    def test_admin_is_protected_and_crud_refreshes_engine(self):
        self.assertEqual(self.client.get("/api/facts").status_code, 401)
        self.assertEqual(self.login().status_code, 302)
        token = self.csrf()
        response = self.client.post("/api/facts", json={"predicate": "doctor", "args": ["priya", ""]}, headers={"X-CSRF-Token": token})
        self.assertEqual(response.status_code, 201)
        self.assertTrue(engine.holds("doctor", ["priya"]))
        self.assertEqual(self.client.post("/api/facts", json={"predicate": "bad-name", "args": ["x"]}, headers={"X-CSRF-Token": token}).status_code, 422)
        self.assertEqual(self.client.post("/api/admin/query", json={"query": "doctor(Doctor)"}, headers={"X-CSRF-Token": token}).status_code, 200)

    def test_state_changes_require_csrf(self):
        self.login()
        response = self.client.post("/api/facts", json={"predicate": "doctor", "args": ["priya"]})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()


class RoleAccessTests(unittest.TestCase):
    """Only the administrator role is supported."""
    def setUp(self):
        self.client = app.app.test_client()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db = auth.USER_DB_PATH
        auth.USER_DB_PATH = os.path.join(self.temp_dir.name, "users.db")
        auth.init_db()
        auth.create_user("manager", "ManagerPassword1", "admin")

    def tearDown(self):
        auth.USER_DB_PATH = self.old_db
        self.temp_dir.cleanup()

    def token(self):
        with self.client.session_transaction() as session:
            return session["csrf_token"]

    def sign_in(self, username, password):
        self.client.get("/login")
        return self.client.post("/login", data={"username": username, "password": password,
                                                  "csrf_token": self.token()}, follow_redirects=False)

    def test_landing_and_roles_redirect_to_admin_login(self):
        landing = self.client.get("/")
        self.assertEqual(landing.status_code, 200)
        self.assertIn(b"Intelligent Hospital FAQ System", landing.data)
        self.assertNotIn(b"Role-Based Access", landing.data)
        self.assertEqual(self.client.get("/roles").status_code, 302)
        self.assertEqual(self.client.get("/dashboard").status_code, 302)

    def test_admin_only_access_and_logout(self):
        self.assertEqual(self.sign_in("manager", "ManagerPassword1").status_code, 302)
        self.assertEqual(self.client.get("/dashboard").status_code, 200)
        self.assertEqual(self.client.get("/knowledge-base").status_code, 200)
        self.assertEqual(self.client.get("/analytics").status_code, 200)
        self.client.post("/logout", data={"csrf_token": self.token()})
        self.assertEqual(self.client.get("/dashboard").status_code, 302)

    def test_admin_api_rejects_non_admin_roles(self):
        self.assertEqual(self.sign_in("manager", "ManagerPassword1").status_code, 302)
        response = self.client.post("/api/admin/users", json={"username": "newadmin", "role": "staff",
                                                                 "password": "NewAdminPassword1"},
                                    headers={"X-CSRF-Token": self.token()})
        self.assertEqual(response.status_code, 422)
        account = self.client.post("/api/admin/users", json={"username": "newadmin", "role": "admin",
                                                              "password": "NewAdminPassword1"},
                                   headers={"X-CSRF-Token": self.token()})
        self.assertEqual(account.status_code, 201)
