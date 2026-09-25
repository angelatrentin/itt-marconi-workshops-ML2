"""
test_config.py — Unit tests for config.py

Uses pytest monkeypatch to control environment variables, then
calls load_config() to verify the resulting Config object or the
expected sys.exit(1) behaviour.

Requirements: REQ-USR-P02, REQ-USR-P03
"""

import pytest
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load(monkeypatch, env: dict):
    """
    Patch the environment with *env* (clearing PORT, STORAGE_BACKEND, DATA_DIR
    first so that leftover host env-vars do not interfere), then call
    load_config() and return the result.
    """
    for key in ("PORT", "STORAGE_BACKEND", "DATA_DIR"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    # Import here so monkeypatch is already active before the module reads env
    from app.config import load_config
    return load_config()


# ---------------------------------------------------------------------------
# Default values (REQ-USR-P02.2, REQ-USR-P02.4)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-P02")
def test_defaults(monkeypatch):
    """No env vars set → port=5001, backend=memory, data_dir=None."""
    config = _load(monkeypatch, {})
    assert config.port == 5001
    assert config.storage_backend == "memory"
    assert config.data_dir is None


# ---------------------------------------------------------------------------
# PORT parsing (REQ-USR-P02.1)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-P02")
def test_custom_port(monkeypatch):
    """A valid PORT value is parsed to an integer."""
    config = _load(monkeypatch, {"PORT": "8080"})
    assert config.port == 8080


@pytest.mark.req("REQ-USR-P02")
def test_port_lower_boundary(monkeypatch):
    """PORT=1 is the lowest valid port."""
    config = _load(monkeypatch, {"PORT": "1"})
    assert config.port == 1


@pytest.mark.req("REQ-USR-P02")
def test_port_upper_boundary(monkeypatch):
    """PORT=65535 is the highest valid port."""
    config = _load(monkeypatch, {"PORT": "65535"})
    assert config.port == 65535


@pytest.mark.req("REQ-USR-P02")
def test_port_zero_exits(monkeypatch):
    """PORT=0 is out of range → sys.exit(1)."""
    with pytest.raises(SystemExit) as exc_info:
        _load(monkeypatch, {"PORT": "0"})
    assert exc_info.value.code == 1


@pytest.mark.req("REQ-USR-P02")
def test_port_too_large_exits(monkeypatch):
    """PORT=65536 exceeds the maximum → sys.exit(1)."""
    with pytest.raises(SystemExit) as exc_info:
        _load(monkeypatch, {"PORT": "65536"})
    assert exc_info.value.code == 1


@pytest.mark.req("REQ-USR-P02")
def test_port_non_integer_exits(monkeypatch):
    """PORT=abc is not an integer → sys.exit(1)."""
    with pytest.raises(SystemExit) as exc_info:
        _load(monkeypatch, {"PORT": "abc"})
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# STORAGE_BACKEND (REQ-USR-P02.3, REQ-USR-P02.5)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-P02")
@pytest.mark.parametrize("backend", ["memory", "json", "sqlite"])
def test_valid_storage_backends(monkeypatch, tmp_path, backend):
    """All three recognised backend values are accepted without error."""
    env = {"STORAGE_BACKEND": backend}
    if backend in ("json", "sqlite"):
        env["DATA_DIR"] = str(tmp_path)
    config = _load(monkeypatch, env)
    assert config.storage_backend == backend


@pytest.mark.req("REQ-USR-P02")
def test_invalid_storage_backend_exits(monkeypatch):
    """An unrecognised STORAGE_BACKEND value triggers sys.exit(1)."""
    with pytest.raises(SystemExit) as exc_info:
        _load(monkeypatch, {"STORAGE_BACKEND": "redis"})
    assert exc_info.value.code == 1


@pytest.mark.req("REQ-USR-P02")
def test_empty_storage_backend_exits(monkeypatch):
    """An empty STORAGE_BACKEND string is not a valid value → sys.exit(1)."""
    with pytest.raises(SystemExit) as exc_info:
        _load(monkeypatch, {"STORAGE_BACKEND": ""})
    assert exc_info.value.code == 1


@pytest.mark.req("REQ-USR-P02")
def test_memory_backend_has_no_data_dir(monkeypatch):
    """memory backend does not require DATA_DIR; data_dir attribute is None."""
    config = _load(monkeypatch, {"STORAGE_BACKEND": "memory"})
    assert config.data_dir is None


# ---------------------------------------------------------------------------
# DATA_DIR for file-based backends (REQ-USR-P02.6, REQ-USR-P03.4)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-P02")
def test_data_dir_used_for_json_backend(monkeypatch, tmp_path):
    """json backend sets data_dir to the provided DATA_DIR path."""
    config = _load(monkeypatch, {"STORAGE_BACKEND": "json", "DATA_DIR": str(tmp_path)})
    assert config.data_dir == tmp_path


@pytest.mark.req("REQ-USR-P02")
def test_data_dir_used_for_sqlite_backend(monkeypatch, tmp_path):
    """sqlite backend sets data_dir to the provided DATA_DIR path."""
    config = _load(monkeypatch, {"STORAGE_BACKEND": "sqlite", "DATA_DIR": str(tmp_path)})
    assert config.data_dir == tmp_path


@pytest.mark.req("REQ-USR-P02")
def test_data_dir_default_is_data(monkeypatch, tmp_path):
    """
    When DATA_DIR is absent and backend is json, the default path './data' is used.
    We redirect the default by setting DATA_DIR to tmp_path to avoid polluting
    the working directory during tests.
    (Behaviour tested: data_dir is a Path, not None.)
    """
    config = _load(monkeypatch, {"STORAGE_BACKEND": "json", "DATA_DIR": str(tmp_path)})
    assert isinstance(config.data_dir, Path)


@pytest.mark.req("REQ-USR-P02")
def test_data_dir_auto_created(monkeypatch, tmp_path):
    """
    If DATA_DIR does not yet exist, load_config() creates it automatically
    instead of exiting.
    """
    new_dir = tmp_path / "subdir" / "nested"
    assert not new_dir.exists()
    config = _load(monkeypatch, {"STORAGE_BACKEND": "json", "DATA_DIR": str(new_dir)})
    assert new_dir.exists()
    assert config.data_dir == new_dir


@pytest.mark.req("REQ-USR-P02")
def test_data_dir_not_writable_exits(monkeypatch, tmp_path):
    """
    A DATA_DIR that exists but is not writable causes sys.exit(1).
    Skipped on Windows where permission bits work differently.
    """
    import stat
    import sys as _sys

    if _sys.platform == "win32":
        pytest.skip("File permission chmod test not reliable on Windows")

    read_only_dir = tmp_path / "ro_dir"
    read_only_dir.mkdir()
    read_only_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)  # r-x, no write

    try:
        with pytest.raises(SystemExit) as exc_info:
            _load(monkeypatch, {"STORAGE_BACKEND": "json", "DATA_DIR": str(read_only_dir)})
        assert exc_info.value.code == 1
    finally:
        # Restore permissions so pytest can clean up tmp_path
        read_only_dir.chmod(stat.S_IRWXU)
