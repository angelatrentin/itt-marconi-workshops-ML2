"""
main.py — Entry point and application factory for user-service.

Bootstrap flow:
  1. config = load_config()           ← reads and validates env vars; exits on error
  2. repo   = select_repository(config) ← instantiates the correct backend
  3. app    = create_app(repo)          ← creates Flask app, registers routes
  4. app.run(host="0.0.0.0", port=config.port)

Requirements: REQ-USR-E07, REQ-USR-P02
"""

from flask import Flask, jsonify

from app.config import load_config


def select_repository(config):
    """
    Instantiate and return the correct AbstractUserRepository implementation
    based on config.storage_backend.

    Imports are done lazily here so that create_app() remains importable even
    before repository.py is fully implemented (useful during incremental development
    and unit tests that supply their own repo instance).

    Requirements: REQ-USR-P03.5
    """
    # Lazy import to avoid hard-coupling at module load time
    from app.repository import (  # noqa: PLC0415
        JsonUserRepository,
        MemoryUserRepository,
        SqliteUserRepository,
    )

    backend = config.storage_backend

    if backend == "memory":
        return MemoryUserRepository()
    elif backend == "json":
        return JsonUserRepository(config.data_dir)
    elif backend == "sqlite":
        return SqliteUserRepository(config.data_dir)
    else:
        # config.py already validates this; this branch is a defensive fallback.
        raise ValueError(f"Unknown storage backend: {backend!r}")


def create_app(repo) -> Flask:
    """
    Application factory: create and configure the Flask application.

    Registers the /health route directly on the app and prepares a Blueprint
    placeholder for the REST API routes (registered by routes.py in later tasks).

    Parameters
    ----------
    repo : AbstractUserRepository
        The repository instance to inject into the request context. It is stored
        on app.config so that route handlers can access it via current_app.config.

    Returns
    -------
    Flask
        Fully configured Flask application instance.

    Requirements: REQ-USR-E07.1–2, REQ-USR-P02.7
    """
    app = Flask(__name__)

    # Inject the repository into Flask's config for access from route handlers.
    app.config["REPO"] = repo

    # ------------------------------------------------------------------
    # GET /health
    # Always returns 200 regardless of backend state (REQ-USR-E07.2).
    # ------------------------------------------------------------------
    @app.route("/health", methods=["GET"])
    def health():
        """Health check — verifies the HTTP process is alive, not the backend."""
        return jsonify({"status": "ok", "service": "user-service"}), 200

    # ------------------------------------------------------------------
    # API Blueprint registration
    # The blueprint is defined in routes.py (tasks 10–15).
    # We register it here as soon as the module is available; during the
    # interim period (before routes.py exists) the health endpoint above
    # is sufficient to satisfy REQ-USR-P02.7.
    # ------------------------------------------------------------------
    try:
        from app.routes import api_blueprint  # noqa: PLC0415

        app.register_blueprint(api_blueprint)
    except ImportError:
        # routes.py has not been implemented yet — this is expected while
        # working through tasks 10–15.  The /health endpoint is still live.
        pass

    return app


# ---------------------------------------------------------------------------
# Bootstrap (only executed when the module is the entry point)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    config = load_config()
    repo = select_repository(config)
    app = create_app(repo)
    app.run(host="0.0.0.0", port=config.port)
