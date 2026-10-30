"""
Security regression tests for the shared-origin hardening.

Run with: uv run python -m unittest discover -s tests
"""

import os
import tempfile
import unittest

os.environ.setdefault("CRUCIBLE_API_KEY", "test-key")

from app.routes import api, backend
from app.spectre_backend import SpectreBackend
from flask import Flask


def _make_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.register_blueprint(api)
    app.testing = True
    return app


class ExportEscapingTests(unittest.TestCase):
    """The generated HTML log must never contain unescaped submitted markup."""

    def test_public_html_escapes_fields(self):
        payload = "<script>alert(1)</script>"
        with tempfile.TemporaryDirectory() as tmp:
            be = SpectreBackend()
            be.log_dir = tmp
            agg = os.path.join(tmp, "spectre_agg.jsonl")
            be._append_jsonl(agg, {
                "type": "logout", "timestamp": "2026-01-01 00:00",
                "user_name": payload, "proposal": payload,
                "proposal_title": payload, "report_public": payload,
                "kv": [payload], "modes": [], "holders": [],
            })
            be._export_public_html(agg)
            with open(os.path.join(tmp, "public_logs", "index.html")) as f:
                html = f.read()
        self.assertNotIn(payload, html)
        self.assertIn("&lt;script&gt;", html)

    def test_admin_html_escapes_fields(self):
        payload = "<img src=x onerror=alert(1)>"
        with tempfile.TemporaryDirectory() as tmp:
            be = SpectreBackend()
            be.log_dir = tmp
            agg = os.path.join(tmp, "spectre_agg.jsonl")
            be._append_jsonl(agg, {
                "type": "logout", "timestamp": "2026-01-01 00:00",
                "user_name": payload, "email": payload, "annotate_private": payload,
                "kv": [], "modes": [], "holders": [],
            })
            be._export_admin_html(agg)
            with open(os.path.join(tmp, "admin_logs", "index.html")) as f:
                html = f.read()
        self.assertNotIn("onerror=alert(1)>", html)
        self.assertIn("&lt;img", html)

    def test_no_hardcoded_password_in_source(self):
        import app.spectre_backend as mod
        with open(mod.__file__) as f:
            self.assertNotIn("spectacular@cell", f.read())


class RequestGuardTests(unittest.TestCase):
    """State-changing requests need a JSON body and an allowed Origin."""

    def setUp(self):
        self.client = _make_app().test_client()
        self.ok_origin = next(iter(__import__("app.routes", fromlist=["ALLOWED_ORIGINS"]).ALLOWED_ORIGINS))

    def test_non_json_post_refused(self):
        r = self.client.post("/api/login", data="x=1",
                             content_type="application/x-www-form-urlencoded",
                             headers={"Origin": self.ok_origin})
        self.assertEqual(r.status_code, 415)

    def test_foreign_origin_refused(self):
        r = self.client.post("/api/login", json={},
                             headers={"Origin": "https://evil.example"})
        self.assertEqual(r.status_code, 403)

    def test_missing_origin_refused(self):
        r = self.client.post("/api/login", json={})
        self.assertEqual(r.status_code, 403)

    def test_allowed_origin_passes_guard(self):
        # Reaches the handler (which may fail later); the guard does not block it.
        r = self.client.post("/api/lookup-user", json={"identifier": ""},
                             headers={"Origin": self.ok_origin})
        self.assertNotIn(r.status_code, (403, 415))

    def test_get_not_blocked(self):
        self.assertEqual(self.client.get("/api/options").status_code, 200)


class LookupDispatchTests(unittest.TestCase):
    """An '@' is looked up by email, anything else by username; neither needs admin."""

    class _FakeUsers:
        def __init__(self):
            self.calls = []

        def get(self, email=None, username=None):
            self.calls.append(("email", email) if email else ("username", username))
            return {"first_name": "A", "last_name": "B", "unique_id": "0000-0001"}

        def get_projects(self, orcid, **kw):
            return [{"project_id": "P1", "title": "Proj", "unique_id": "mfid-1"}]

    def _backend_with_fake(self):
        be = SpectreBackend()
        fake = self._FakeUsers()
        be.client = type("C", (), {"users": fake})()
        return be, fake

    def test_email_uses_email_lookup(self):
        be, fake = self._backend_with_fake()
        res = be.lookup_user("a@lbl.gov")
        self.assertTrue(res["ok"])
        self.assertEqual(fake.calls, [("email", "a@lbl.gov")])
        self.assertEqual(res["proposals"], [{"code": "P1", "title": "Proj"}])

    def test_username_uses_username_lookup(self):
        be, fake = self._backend_with_fake()
        res = be.lookup_user("someuser")
        self.assertTrue(res["ok"])
        self.assertEqual(fake.calls, [("username", "someuser")])

    def test_blank_identifier_refused(self):
        be, _ = self._backend_with_fake()
        self.assertFalse(be.lookup_user("  ")["ok"])


if __name__ == "__main__":
    unittest.main()
