# Deployment

The SPECTRE logbook is a Flask web app served under `https://crucible.lbl.gov/spectre-logging/`. In production it runs on Cloud Run (`spectre-logbook`, project `mf-crucible`, region `us-central1`), reached through the `crucible-web` nginx proxy, which restricts it to LBL networks. It is built and deployed from `cloudbuild.yaml` on push.

## Serving

Production runs under gunicorn (see the `Dockerfile`); never the Flask development server, so the interactive debugger is never exposed. One worker: the backend keeps per-session state in memory, so several workers would split a user's session.

## Environment variables

| Variable | Purpose |
| --- | --- |
| `CRUCIBLE_API_KEY` | Crucible service-account key used for user and project lookups. It needs only the **contributor** platform role: exact email and username lookups and listing a user's projects all work with global read, not administrator rights. Do not give the logbook an admin key. |
| `SPECTRE_ADMIN_PASSWORD` | Gates the admin CSV download and option editing. |
| `SPECTRE_ALLOWED_ORIGINS` | Comma-separated origins allowed to make state-changing (POST) requests. Defaults to `https://crucible.lbl.gov`. For local development, set `http://localhost:7788`. |

State-changing requests must send `Content-Type: application/json` and an `Origin` in `SPECTRE_ALLOWED_ORIGINS`; this keeps a page on another site from posting to the logbook even though it shares an origin with the rest of `crucible.lbl.gov`.

## Secrets (Secret Manager)

`cloudbuild.yaml` injects:
- `CRUCIBLE_API_KEY` from secret `spectre-logbook-crucible-apikey` (a contributor service-account key, used only by this service),
- `SPECTRE_ADMIN_PASSWORD` from secret `spectre-logbook-password`.

The Cloud Run runtime service account (`spectre-logbook-cloudrun@mf-crucible.iam.gserviceaccount.com`) needs `roles/secretmanager.secretAccessor` on both.

## Local development

```bash
export CRUCIBLE_API_KEY=<a contributor key>   # any non-empty value boots it; a real key is needed for lookups
export SPECTRE_ALLOWED_ORIGINS=http://localhost:7788
uv run gunicorn --bind 127.0.0.1:7788 --workers 1 server:app
```

Then open `http://localhost:7788`. Run the tests with `uv run python -m unittest discover -s tests`.
