"""
Entry point. Run with `python run.py` (respects FLASK_PORT from .env),
or `flask --app run run` (respects FLASK_RUN_PORT from .env).
"""
import os
from dotenv import load_dotenv

load_dotenv()  # must happen BEFORE create_app so config picks up .env

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 5003))
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    print(f"🚀 Starting on http://{host}:{port}")
    app.run(debug=debug, host=host, port=port)
