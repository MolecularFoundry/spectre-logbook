"""
SPECTRE Logbook — Flask web app entry point.
"""

from flask import Flask
from app.routes import api


def create_app():
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.register_blueprint(api)
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=7788, debug=True)
