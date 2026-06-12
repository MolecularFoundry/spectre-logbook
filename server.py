"""
SPECTRE Logbook — Flask web app entry point.
"""

import os

from flask import Flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware

from app.routes import api


def _not_found(environ, start_response):
    start_response("404 Not Found", [("Content-Type", "text/plain")])
    return [b"Not Found"]


def create_app():
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.register_blueprint(api)

    # In the cloud the app is served under a path prefix (e.g. /spectre-logging).
    # Mounting the whole WSGI app there keeps every route — pages, /api and
    # /static — under the prefix and sets SCRIPT_NAME so redirects/url_for stay
    # correct. Local runs leave URL_PREFIX unset and serve from root.
    prefix = os.environ.get("URL_PREFIX", "").rstrip("/")
    if prefix:
        app.wsgi_app = DispatcherMiddleware(_not_found, {prefix: app.wsgi_app})

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=7788, debug=True)
