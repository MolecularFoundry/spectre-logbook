"""
SPECTRE Logbook — Flask web app entry point.
"""

import os

from flask import Flask
from app.routes import api


class ReverseProxied:
    """WSGI middleware that respects X-Forwarded-Prefix / SCRIPT_NAME
    set by a reverse proxy so that url_for() generates correct paths."""

    def __init__(self, app, script_name=None):
        self.app = app
        self.script_name = script_name

    def __call__(self, environ, start_response):
        script_name = environ.get("HTTP_X_FORWARDED_PREFIX", "") or self.script_name
        if script_name:
            environ["SCRIPT_NAME"] = script_name
            path_info = environ.get("PATH_INFO", "")
            if path_info.startswith(script_name):
                environ["PATH_INFO"] = path_info[len(script_name):]
        return self.app(environ, start_response)


def create_app():
    prefix = os.environ.get("SCRIPT_NAME", "")

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.register_blueprint(api)

    if prefix:
        app.wsgi_app = ReverseProxied(app.wsgi_app, script_name=prefix)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=7788, debug=True)
