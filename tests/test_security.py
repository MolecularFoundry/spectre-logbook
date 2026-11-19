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


class LookupTests(unittest.TestCase):
    """Lookups pass the identifier to users.get() and list projects by unique_id."""

    class _FakeUsers:
        def __init__(self, user):
            self.user = user
            self.calls = []

        def get(self, user_ref):
            self.calls.append(("get", user_ref))
            return self.user

        def list_projects(self, user_ref, **kw):
            self.calls.append(("list_projects", user_ref))
            return [{"project_id": "P1", "title": "Proj", "unique_id": "mfid-1"}]

    def _backend_with_fake(self, **user):
        be = SpectreBackend()
        fake = self._FakeUsers({"first_name": "A", "last_name": "B", "username": "ab", **user})
        be.client = type("C", (), {"users": fake})()
        return be, fake

    def test_email_lookup(self):
        be, fake = self._backend_with_fake(unique_id="0000-0002-1825-0097")
        res = be.lookup_user("a@lbl.gov")
        self.assertTrue(res["ok"])
        self.assertEqual(fake.calls, [("get", "a@lbl.gov"),
                                      ("list_projects", "0000-0002-1825-0097")])
        self.assertEqual(res["proposals"], [{"code": "P1", "title": "Proj"}])
        self.assertEqual(res["email"], "a@lbl.gov")
        self.assertEqual(res["username"], "ab")
        self.assertEqual(res["orcid"], "0000-0002-1825-0097")

    def test_username_lookup_has_no_email(self):
        be, fake = self._backend_with_fake(unique_id="0000-0002-1825-0097")
        res = be.lookup_user("ab")
        self.assertTrue(res["ok"])
        self.assertEqual(fake.calls[0], ("get", "ab"))
        self.assertEqual(res["email"], "")

    def test_mfid_user_takes_orcid_from_orcid_field(self):
        mfid = "0abcdefghjkmnpqrstvwxyz123"
        be, fake = self._backend_with_fake(unique_id=mfid, orcid="0000-0002-1825-0097")
        res = be.lookup_user("ab")
        self.assertEqual(res["orcid"], "0000-0002-1825-0097")
        self.assertEqual(fake.calls[1], ("list_projects", mfid))

    def test_mfid_user_without_orcid_leaves_it_blank(self):
        be, _ = self._backend_with_fake(unique_id="0abcdefghjkmnpqrstvwxyz123")
        self.assertEqual(be.lookup_user("ab")["orcid"], "")

    def test_blank_identifier_refused(self):
        be, _ = self._backend_with_fake()
        self.assertFalse(be.lookup_user("  ")["ok"])


class AdminPasswordTests(unittest.TestCase):
    """No admin password configured means no admin access, even with ''."""

    def test_unset_password_refuses_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            be = SpectreBackend()
            be.log_dir = tmp
            be.admin_password = ""
            _, csv_path = be._agg_paths()
            open(csv_path, "w").close()
            self.assertIsNone(be.get_admin_csv_path(""))
            self.assertIsNone(be.get_admin_csv_path("   "))

    def test_correct_password_returns_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            be = SpectreBackend()
            be.log_dir = tmp
            be.admin_password = "s3cret"
            _, csv_path = be._agg_paths()
            open(csv_path, "w").close()
            self.assertEqual(be.get_admin_csv_path("s3cret"), csv_path)
            self.assertIsNone(be.get_admin_csv_path("wrong"))


class UsernameLoggingTests(unittest.TestCase):
    """A username login is logged as a username, not in the email column."""

    def test_username_kept_out_of_email(self):
        with tempfile.TemporaryDirectory() as tmp:
            be = SpectreBackend()
            be.log_dir = tmp
            be._safe_run_sync = lambda: None
            be.start_session({"user_name": "A B", "email": "", "username": "ab"})
            agg, _ = be._agg_paths()
            evt = be._read_jsonl(agg)[-1]
        self.assertEqual(evt["email"], "")
        self.assertEqual(evt["username"], "ab")


if __name__ == "__main__":
    unittest.main()
