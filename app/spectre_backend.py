"""
SpectreBackend — pure-Python business logic for the SPECTRE Microscope Logbook.

Extracted from the PyQt SpectreControlPanel. No Qt, no rclone, no RabbitMQ.
All methods accept and return plain dicts.

Credentials:
  - CRUCIBLE_API_KEY env var (used by CrucibleClient automatically)
  - SPECTRE_ADMIN_PASSWORD env var (gates admin CSV download)
"""

import csv
import json
import os
import re
import uuid
import subprocess
from datetime import datetime

from crucible import CrucibleClient


class SpectreBackend:

    def __init__(self):
        self.log_dir = os.path.join(os.getcwd(), "runtime", "spectre_logs")
        os.makedirs(self.log_dir, exist_ok=True)

        self.session_id = None
        self.logged_in = False
        self.login_time = ""
        self.logout_time = ""
        self._current_event_type = ""
        self.title_cache = {}
        self.project_map = {}
        self.current_project_title = ""

        # Per-session file paths (set on login)
        self.user_log_path = None
        self.session_data = {}

        # Crucible client (reads api_key and api_url from env)
        self.client = CrucibleClient(api_url = 'https://crucible.lbl.gov/api/v2', api_key = os.environ.get("CRUCIBLE_API_KEY", ""))

        # Admin password from env
        self.admin_password = os.environ.get("SPECTRE_ADMIN_PASSWORD", "")

        # Shipped default options (seed for the editable runtime copy)
        self.default_options_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "options.json"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _safe(self, s):
        return re.sub(r'[^A-Za-z0-9._-]+', '_', s.strip())[:80] if s else ""

    def _now(self):
        return datetime.now().isoformat(sep=' ', timespec='minutes')

    def _ensure_dirs(self):
        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(os.path.join(self.log_dir, "user_logs"), exist_ok=True)
        os.makedirs(os.path.join(self.log_dir, "public_logs"), exist_ok=True)
        os.makedirs(os.path.join(self.log_dir, "admin_logs"), exist_ok=True)

    def _agg_paths(self):
        agg_json = os.path.join(self.log_dir, "spectre_agg.json")
        admin_csv = os.path.join(self.log_dir, "admin_logs", "spectre_admin_log.csv")
        os.makedirs(os.path.dirname(admin_csv), exist_ok=True)
        return agg_json, admin_csv

    def _read_json_list(self, path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except FileNotFoundError:
            return []
        except Exception as e:
            print(f"[Spectre] Could not read JSON list from {path}: {e}")
            return []

    def _write_json_list(self, path, arr):
        with open(path, "w") as f:
            json.dump(arr, f, indent=4)

    # ------------------------------------------------------------------
    # Snapshot / log-data collection
    # ------------------------------------------------------------------
    def _collect_log_data(self, data):
        return dict(
            user_name=data.get("user_name", ""),
            email=data.get("email", ""),
            proposal=data.get("proposal", ""),
            kv=data.get("kv", []),
            modes=data.get("modes", []),
            holders=data.get("holders", []),
            holder_other=data.get("holder_other", ""),
            annotate_private=data.get("annotate_private", ""),
            report_public=data.get("report_public", ""),
        )

    def _snapshot(self, data):
        snap = self._collect_log_data(data)
        snap["proposal_title"] = self.current_project_title
        snap["session_id"] = self.session_id
        snap["session_name"] = data.get("session_name", "")
        snap["login_timestamp"] = self.login_time
        snap["logout_timestamp"] = self.logout_time
        return snap

    # ------------------------------------------------------------------
    # Event persistence
    # ------------------------------------------------------------------
    def _append_event_into_session_file(self, path, data):
        try:
            with open(path, "r") as f:
                doc = json.load(f)
        except (FileNotFoundError, Exception):
            doc = {"session": {}, "events": []}

        evt = {
            "type": self._current_event_type,
            "timestamp": self._now(),
            "snapshot": self._snapshot(data),
        }
        if not doc.get("session"):
            doc["session"] = {
                "user_name": evt["snapshot"].get("user_name", ""),
                "email": evt["snapshot"].get("email", ""),
                "session_id": self.session_id,
                "session_name": evt["snapshot"].get("session_name", ""),
                "proposal": evt["snapshot"].get("proposal", ""),
                "proposal_title": evt["snapshot"].get("proposal_title", ""),
                "start_timestamp": self.login_time,
            }
        doc["events"].append(evt)

        with open(path, "w") as f:
            json.dump(doc, f, indent=4)

    def _append_to_admin_csv(self, csv_path, event_dict):
        header = [
            "event_type", "timestamp", "session_id", "user_name", "email",
            "session_name", "proposal", "proposal_title", "kv", "modes", "holders",
            "holder_other", "report_public", "annotate_private", "login_timestamp", "logout_timestamp",
        ]
        existed = os.path.exists(csv_path)
        with open(csv_path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=header)
            if not existed:
                w.writeheader()
            row = {
                "event_type": event_dict.get("type", ""),
                "timestamp": event_dict.get("timestamp", ""),
                "session_id": event_dict.get("session_id", ""),
                "user_name": event_dict.get("user_name", ""),
                "email": event_dict.get("email", ""),
                "session_name": event_dict.get("session_name", ""),
                "proposal": event_dict.get("proposal", ""),
                "proposal_title": event_dict.get("proposal_title", ""),
                "kv": ", ".join(event_dict.get("kv", [])),
                "modes": ", ".join(event_dict.get("modes", [])),
                "holders": ", ".join(event_dict.get("holders", [])),
                "holder_other": event_dict.get("holder_other", ""),
                "report_public": event_dict.get("report_public", ""),
                "annotate_private": event_dict.get("annotate_private", ""),
                "login_timestamp": event_dict.get("login_timestamp", ""),
                "logout_timestamp": event_dict.get("logout_timestamp", ""),
            }
            w.writerow(row)

    def _append_to_aggregates(self, evt_type, data):
        agg_json, admin_csv = self._agg_paths()
        base = self._snapshot(data)
        base["type"] = evt_type
        base["timestamp"] = self._now()

        arr = self._read_json_list(agg_json)
        arr.append(base.copy())
        self._write_json_list(agg_json, arr)

        self._append_to_admin_csv(admin_csv, base)

        try:
            self._export_public_html(agg_json)
            self._export_admin_html(agg_json)
            self._export_main_index()
        except Exception as e:
            print(f"[Spectre] HTML export failed: {e}")

        self._safe_run_sync()

    def _safe_run_sync(self):
        try:
            repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../"))
            sh_script = os.path.join(repo_root, "scripts", "sync_logbook_site.sh")
            ps_script = os.path.join(repo_root, "scripts", "sync_logbook_site.ps1")
            if os.name == "nt" and os.path.exists(ps_script):
                subprocess.run(
                    ["powershell", "-ExecutionPolicy", "Bypass", "-File", ps_script],
                    check=True,
                )
            elif os.path.exists(sh_script):
                subprocess.run([sh_script], check=True)
        except Exception as e:
            print(f"[Spectre] Post-export sync skipped: {e}")

    # ------------------------------------------------------------------
    # HTML exports
    # ------------------------------------------------------------------
    def _export_public_html(self, agg_json_path):
        out_dir = os.path.join(self.log_dir, "public_logs")
        os.makedirs(out_dir, exist_ok=True)
        out_html = os.path.join(out_dir, "index.html")
        data = self._read_json_list(agg_json_path)
        rows = []
        for e in data:
            rows.append({
                "timestamp": e.get("timestamp", ""),
                "user": e.get("user_name", ""),
                "session": e.get("session_name", ""),
                "proposal": e.get("proposal", ""),
                "title": e.get("proposal_title", ""),
                "kv": ", ".join(e.get("kv", [])),
                "modes": ", ".join(e.get("modes", [])),
                "holders": ", ".join(e.get("holders", [])),
                "report": e.get("report_public", ""),
            })
        html = [
            "<!DOCTYPE html>",
            "<meta charset='utf-8'>",
            "<title>SPECTRE Public Log</title>",
            "<style>body{font-family:Arial,sans-serif;margin:16px}table{border-collapse:collapse;width:100%}"
            "th,td{border:1px solid #ddd;padding:8px}th{background:#f8f8f8;position:sticky;top:0}</style>",
            "<h2>SPECTRE — Public Log Viewer</h2>",
            "<table><thead><tr><th>Timestamp</th><th>User</th><th>Session</th><th>Proposal</th>"
            "<th>Title</th><th>kV</th><th>Modes</th><th>Holders</th><th>Report</th></tr></thead><tbody>",
        ]
        for r in rows:
            html.append(
                f"<tr><td>{r['timestamp']}</td><td>{r['user']}</td><td>{r['session']}</td>"
                f"<td>{r['proposal']}</td><td>{r['title']}</td><td>{r['kv']}</td>"
                f"<td>{r['modes']}</td><td>{r['holders']}</td><td>{r['report']}</td></tr>"
            )
        html.append("</tbody></table>")
        with open(out_html, "w", encoding="utf-8") as f:
            f.write("\n".join(html))

    def _export_admin_html(self, agg_json_path):
        out_dir = os.path.join(self.log_dir, "admin_logs")
        os.makedirs(out_dir, exist_ok=True)
        out_html = os.path.join(out_dir, "index.html")
        data = self._read_json_list(agg_json_path)
        rows = []
        for e in data:
            rows.append({
                "timestamp": e.get("timestamp", ""),
                "user": e.get("user_name", ""),
                "email": e.get("email", ""),
                "session": e.get("session_name", ""),
                "proposal": e.get("proposal", ""),
                "title": e.get("proposal_title", ""),
                "kv": ", ".join(e.get("kv", [])),
                "modes": ", ".join(e.get("modes", [])),
                "holders": ", ".join(e.get("holders", [])),
                "report": e.get("report_public", ""),
                "private": e.get("annotate_private", ""),
            })
        html = [
            "<!DOCTYPE html>",
            "<meta charset='utf-8'>",
            "<title>SPECTRE Admin Logbook</title>",
            "<style>body{font-family:Arial;margin:16px}table{border-collapse:collapse;width:100%}"
            "th,td{border:1px solid #ccc;padding:8px}th{background:#f0f0f0;position:sticky;top:0}"
            "input{margin-bottom:10px;padding:6px;width:30%}</style>",
            "<h2>SPECTRE — Admin Logbook</h2>",
            "<input type='text' id='filterInput' placeholder='Search...'>",
            "<table id='logTable'><thead><tr>"
            "<th>Timestamp</th><th>User</th><th>Email</th><th>Session</th>"
            "<th>Proposal</th><th>Title</th><th>kV</th><th>Modes</th><th>Holders</th>"
            "<th>Report</th><th>Private Notes</th></tr></thead><tbody>",
        ]
        for r in rows:
            html.append(
                f"<tr><td>{r['timestamp']}</td><td>{r['user']}</td><td>{r['email']}</td>"
                f"<td>{r['session']}</td><td>{r['proposal']}</td><td>{r['title']}</td>"
                f"<td>{r['kv']}</td><td>{r['modes']}</td><td>{r['holders']}</td>"
                f"<td>{r['report']}</td><td>{r['private']}</td></tr>"
            )
        html.append(
            "</tbody></table>"
            "<script>"
            "const input=document.getElementById('filterInput');"
            "input.addEventListener('keyup',()=>{"
            "const f=input.value.toLowerCase();"
            "for(const row of document.querySelectorAll('#logTable tbody tr')){"
            "row.style.display=row.innerText.toLowerCase().includes(f)?'':'none';}});"
            "</script>"
        )
        with open(out_html, "w", encoding="utf-8") as f:
            f.write("\n".join(html))

    def _export_main_index(self):
        root_html = os.path.join(self.log_dir, "index.html")
        html = [
            "<!DOCTYPE html><meta charset='utf-8'>",
            "<title>SPECTRE Logbook Portal</title>",
            "<style>body{font-family:Arial;margin:60px;text-align:center}"
            "button{padding:10px 20px;margin:10px;font-size:16px;}</style>",
            "<h1>SPECTRE Logbook Portal</h1>",
            "<p>Default view: Public Logbook</p>",
            "<iframe src='public_logs/index.html' width='100%' height='600'></iframe><br>",
            "<button onclick='openAdmin()'>Admin Logbook Access</button>",
            "<script>"
            "function openAdmin(){"
            "let p=prompt('Enter admin password:');"
            "if(p==='spectacular@cell'){window.location.href=\"admin_logs/index.html\";}"
            "else if(p!==null){alert('Incorrect password.');}}"
            "</script>",
        ]
        with open(root_html, "w", encoding="utf-8") as f:
            f.write("\n".join(html))

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------
    def start_session(self, data):
        self._ensure_dirs()
        self.session_id = str(uuid.uuid4())[:8]
        self.logged_in = True
        self.login_time = self._now()
        self.logout_time = ""

        name = data.get("user_name", "").strip() or "Unknown"
        email = data.get("email", "").strip()
        proposal = data.get("proposal", "")
        session_name = data.get("session_name", "").strip()

        self.session_data = {
            "user_name": name,
            "email": email,
            "proposal": proposal,
            "session_name": session_name,
            "orcid": data.get("orcid", "").strip(),
            "kv": [],
            "modes": [],
            "holders": [],
            "holder_other": "",
            "annotate_private": "",
            "report_public": "",
        }

        date_tag = datetime.today().strftime("%Y%m%d")
        time_tag = datetime.today().strftime("%H%M%S")

        user_logs_dir = os.path.join(self.log_dir, "user_logs")
        runtime_json_name = (
            f"user_{date_tag}_{self._safe(name)}_{self._safe(session_name)}"
            f"_{time_tag}_{self.session_id}.json"
        )
        self.user_log_path = os.path.join(user_logs_dir, runtime_json_name)

        self._current_event_type = "login"
        self._append_event_into_session_file(self.user_log_path, self.session_data)
        self._append_to_aggregates("login", self.session_data)

        return {
            "ok": True,
            "session_id": self.session_id,
            "user_name": name,
            "email": email,
            "proposal": proposal,
            "proposal_title": self.current_project_title,
            "login_time": self.login_time,
            "log_path": self.user_log_path,
        }

    def update_metadata(self, data):
        if not self.logged_in:
            return {"ok": False, "error": "Not logged in. Please login first."}

        kv = data.get("kv", [])
        holders = data.get("holders", [])
        missing = []
        if not kv:
            missing.append("kV")
        if not holders:
            missing.append("Holder")
        if missing:
            return {"ok": False, "error": f"Please select: {', '.join(missing)}."}

        if not self.user_log_path:
            return {"ok": False, "error": "No active session file."}

        merged = {**self.session_data, **data}
        self.session_data = merged

        self._current_event_type = "update"
        self._append_event_into_session_file(self.user_log_path, merged)
        self._append_to_aggregates("update", merged)

        return {"ok": True, "message": "Session metadata updated successfully."}

    def save_and_logout(self, data):
        if not self.logged_in:
            return {"ok": False, "error": "Not logged in."}

        kv = data.get("kv", [])
        holders = data.get("holders", [])
        missing = []
        if not kv:
            missing.append("kV")
        if not holders:
            missing.append("Holder")
        if missing:
            return {"ok": False, "error": f"Please select: {', '.join(missing)}."}

        merged = {**self.session_data, **data}
        self.logout_time = self._now()
        self._current_event_type = "logout"

        self._append_event_into_session_file(self.user_log_path, merged)
        self._append_to_aggregates("logout", merged)

        self.logged_in = False
        self.session_id = None
        self.current_project_title = ""
        self.session_data = {}

        return {
            "ok": True,
            "message": "Logout event saved. Session complete.",
            "upload_redirect": None,
        }

    # ------------------------------------------------------------------
    # Email / project lookups (via CrucibleClient)
    # ------------------------------------------------------------------
    def lookup_email(self, email):
        if not email or "@lbl.gov" not in email:
            return {"ok": False, "error": "Enter a valid @lbl.gov email."}

        try:
            user_info = self.client.users.get(email=email)
            if not user_info:
                return {"ok": False, "error": "User not found."}

            full_name = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip()
            orcid = user_info.get("unique_id", "")

            # Get projects for this user
            projects = []
            if orcid:
                projects = self.client.users.get_projects(orcid)

            project_options = []
            for p in projects:
                code = p.get("project_id", "")
                title = p.get("title", "")
                if code:
                    self.title_cache[code] = title
                    self.project_map[code] = p.get("id", "")
                    project_options.append({"code": code, "title": title})

            return {
                "ok": True,
                "name": full_name,
                "orcid": orcid,
                "proposals": project_options,
            }
        except Exception as e:
            print(f"[Spectre] Email lookup failed: {e}")
            return {"ok": False, "error": str(e)}

    def get_proposal_title(self, proposal_code):
        if not proposal_code or proposal_code.startswith("No projects"):
            return ""

        if proposal_code in self.title_cache:
            self.current_project_title = self.title_cache[proposal_code]
            return self.title_cache[proposal_code]

        try:
            project = self.client.projects.get(proposal_code)
            if project:
                title = str(project.get("title") or "").strip()
                if title:
                    self.title_cache[proposal_code] = title
                    self.current_project_title = title
                    return title
        except Exception as e:
            print(f"[Spectre] Error fetching project {proposal_code}: {e}")

        return ""

    def preload_all_titles(self):
        try:
            projects = self.client.projects.list()
            self.project_map = {}
            self.title_cache = {}
            for p in projects:
                pid = p.get("id")
                code = str(p.get("project_id") or "").strip()
                title = str(p.get("title") or "").strip()
                if not pid or not code:
                    continue
                self.project_map[code] = pid
                self.title_cache[code] = title
            print(f"[Spectre] Cached {len(self.title_cache)} project titles.")
        except Exception as e:
            print(f"[Spectre] Error preloading titles: {e}")

    # ------------------------------------------------------------------
    # Public log viewer
    # ------------------------------------------------------------------
    def get_public_logs(self):
        agg_json, _ = self._agg_paths()
        data = self._read_json_list(agg_json)
        rows = []
        for e in data:
            if e.get("type") != "logout":
                continue
            rows.append({
                "timestamp": e.get("timestamp", ""),
                "user": e.get("user_name", ""),
                "session": e.get("session_name", ""),
                "proposal": e.get("proposal", ""),
                "title": e.get("proposal_title", ""),
                "kv": ", ".join(e.get("kv", [])),
                "modes": ", ".join(e.get("modes", [])),
                "holders": ", ".join(e.get("holders", [])),
                "report": e.get("report_public", ""),
            })
        rows.sort(key=lambda r: r["timestamp"], reverse=True)
        return rows

    # ------------------------------------------------------------------
    # Editable option lists (kV / detectors-modes / holders)
    # ------------------------------------------------------------------
    def _options_path(self):
        return os.path.join(self.log_dir, "options.json")

    def _load_default_options(self):
        try:
            with open(self.default_options_path, "r", encoding="utf-8") as f:
                opts = json.load(f)
        except Exception as e:
            print(f"[Spectre] Could not read default options: {e}")
            opts = {}
        return {
            "kv": list(opts.get("kv", [])),
            "modes": list(opts.get("modes", [])),
            "holders": list(opts.get("holders", [])),
        }

    def get_options(self):
        path = self._options_path()
        if not os.path.exists(path):
            opts = self._load_default_options()
            try:
                os.makedirs(self.log_dir, exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(opts, f, indent=4, ensure_ascii=False)
            except Exception as e:
                print(f"[Spectre] Could not seed options.json: {e}")
            return opts
        try:
            with open(path, "r", encoding="utf-8") as f:
                opts = json.load(f)
            return {
                "kv": list(opts.get("kv", [])),
                "modes": list(opts.get("modes", [])),
                "holders": list(opts.get("holders", [])),
            }
        except Exception as e:
            print(f"[Spectre] Could not read options.json: {e}")
            return self._load_default_options()

    def update_options(self, password, options):
        if not self.admin_password or password.strip() != self.admin_password:
            return {"ok": False, "error": "Incorrect admin password."}

        def _clean(values):
            seen, out = set(), []
            for v in values or []:
                v = str(v).strip()
                if v and v not in seen:
                    seen.add(v)
                    out.append(v)
            return out

        cleaned = {
            "kv": _clean(options.get("kv")),
            "modes": _clean(options.get("modes")),
            "holders": _clean(options.get("holders")),
        }
        try:
            os.makedirs(self.log_dir, exist_ok=True)
            with open(self._options_path(), "w", encoding="utf-8") as f:
                json.dump(cleaned, f, indent=4, ensure_ascii=False)
        except Exception as e:
            return {"ok": False, "error": f"Could not save options: {e}"}
        return {"ok": True, "options": cleaned}

    def get_admin_csv_path(self, password):
        if password.strip() != self.admin_password:
            return None
        _, admin_csv = self._agg_paths()
        if os.path.exists(admin_csv):
            return admin_csv
        return None
