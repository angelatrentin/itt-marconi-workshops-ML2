"""
config.py — Configuration loading and validation for user-service.

Reads environment variables, validates values, and terminates the process
with a meaningful error message if the configuration is invalid.

Requirements: REQ-USR-P02, REQ-USR-P03
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

# Valid storage backends
VALID_BACKENDS = {"memory", "json", "sqlite"}

# Backends that require a DATA_DIR
FILE_BACKENDS = {"json", "sqlite"}


@dataclass
class Config:
    """Validated runtime configuration for user-service."""

    port: int
    storage_backend: str  # "memory" | "json" | "sqlite"
    data_dir: Path | None  # None when backend is "memory"


def load_config() -> Config:
    """
    Read environment variables, validate them, and return a Config instance.

    Exits with status 1 and an error message on stderr if:
    - STORAGE_BACKEND contains an unrecognised value
    - STORAGE_BACKEND is json/sqlite and DATA_DIR is missing or not writable

    Requirements: REQ-USR-P02.1–7, REQ-USR-P03.4
    """
    # --- PORT ---
    # REQ-USR-P02.1: read PORT; REQ-USR-P02.2: default 5001
    raw_port = os.environ.get("PORT", "5001")
    try:
        port = int(raw_port)
    except ValueError:
        print(
            f"ERROR: PORT must be an integer between 1 and 65535, got: {raw_port!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    if not (1 <= port <= 65535):
        print(
            f"ERROR: PORT must be between 1 and 65535, got: {port}",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- STORAGE_BACKEND ---
    # REQ-USR-P02.3: read STORAGE_BACKEND; REQ-USR-P02.4: default "memory"
    storage_backend = os.environ.get("STORAGE_BACKEND", "memory")

    # REQ-USR-P02.5: terminate on unrecognised value
    if storage_backend not in VALID_BACKENDS:
        print(
            f"ERROR: Unrecognised STORAGE_BACKEND value: {storage_backend!r}. "
            f"Allowed values are: {', '.join(sorted(VALID_BACKENDS))}",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- DATA_DIR ---
    data_dir: Path | None = None

    if storage_backend in FILE_BACKENDS:
        # REQ-USR-P02.6: default DATA_DIR is ./data
        raw_data_dir = os.environ.get("DATA_DIR", "./data")
        data_dir = Path(raw_data_dir)

        # REQ-USR-P03.4: terminate if DATA_DIR is not writable/accessible
        _validate_data_dir(data_dir)

    return Config(port=port, storage_backend=storage_backend, data_dir=data_dir)


def _validate_data_dir(data_dir: Path) -> None:
    """
    Ensure DATA_DIR exists and is writable, or can be created.

    Tries to create the directory if it does not exist. Exits the process
    with status 1 if the directory cannot be used.

    Requirements: REQ-USR-P03.4
    """
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(
            f"ERROR: Cannot create DATA_DIR {str(data_dir)!r}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Check write access by attempting to create a temporary file
    test_file = data_dir / ".write_test"
    try:
        test_file.touch()
        test_file.unlink()
    except OSError as exc:
        print(
            f"ERROR: DATA_DIR {str(data_dir)!r} is not writable: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
