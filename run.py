"""Application entrypoint for MediLab AI.

Allows running the Flask application server directly via CLI or inside a Docker container.
"""

import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    host = os.getenv("HOST", "0.0.0.0")
    debug = app.config.get("DEBUG", False)

    app.run(host=host, port=port, debug=debug)
