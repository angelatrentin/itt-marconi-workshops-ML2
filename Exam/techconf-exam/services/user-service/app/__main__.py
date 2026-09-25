"""
__main__.py — allows the app package to be run with `python -m app`.

This is the entry point used by services.yaml:
    command: python -m app

It delegates entirely to main.py's bootstrap logic.

Requirements: REQ-USR-P02.7
"""

from app.main import create_app, select_repository
from app.config import load_config

if __name__ == "__main__":
    config = load_config()
    repo = select_repository(config)
    app = create_app(repo)
    app.run(host="0.0.0.0", port=config.port)
