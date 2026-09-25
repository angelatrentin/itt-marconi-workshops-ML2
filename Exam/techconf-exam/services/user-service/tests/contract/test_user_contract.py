"""
test_user_contract.py — Contract tests for user-service.

Each test drives the Flask test client (with an in-memory repository) against a
success response of every endpoint and asserts that the response conforms to the
OpenAPI contract declared in ``contracts/openapi/user-service.yaml`` via the
shared, non-modifiable helper ``contracts.validator.assert_matches_contract``.

The Werkzeug test-client response exposes ``.json`` as a *property* (not a
callable), which the validator's ``requests.Response``-style adapter cannot use.
We therefore always pass the plain ``dict`` form the validator also accepts:

    {"status_code": int, "headers": {...}, "json": <body>}

Requirements: REQ-USR-F01.1–7, REQ-USR-P01.1
"""

import os
import sys

import pytest

# ---------------------------------------------------------------------------
# Make the repo-root ``contracts`` package importable.
#
# This test file lives at:
#   techconf-exam/services/user-service/tests/contract/test_user_contract.py
# The ``contracts`` package lives at:
#   techconf-exam/contracts/
# so the repo root is four levels up from this file's directory.
# ---------------------------------------------------------------------------
REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
assert os.path.isfile(
    os.path.join(REPO_ROOT, "contracts", "validator.py")
), f"contracts/validator.py not found under computed REPO_ROOT={REPO_ROOT!r}"
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from contracts.validator import assert_matches_contract  # noqa: E402

from app.main import create_app  # noqa: E402
from app.repository import MemoryUserRepository  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------
@pytest.fixture()
def client():
    """A fresh Flask test client backed by an isolated in-memory repository."""
    return create_app(MemoryUserRepository()).test_client()


def _contract_response(resp):
    """
    Adapt a Werkzeug test-client response into the plain dict shape the
    validator accepts, avoiding the ``.json`` property vs ``.json()`` pitfall.
    """
    return {
        "status_code": resp.status_code,
        "headers": dict(resp.headers),
        "json": resp.get_json(),
    }


def _create_user(client, **overrides):
    """Create a user via the API and return the parsed User body."""
    payload = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        "company": "Analytical Engines",
        "role": "speaker",
    }
    payload.update(overrides)
    resp = client.post("/api/v1/users", json=payload)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


# ---------------------------------------------------------------------------
# Contract tests — one per success response.
# ---------------------------------------------------------------------------
@pytest.mark.req("REQ-USR-F01")
def test_post_users_matches_contract(client):
    """POST /api/v1/users -> 201 conforms to the ``User`` schema."""
    resp = client.post(
        "/api/v1/users",
        json={
            "first_name": "Grace",
            "last_name": "Hopper",
            "email": "grace@example.com",
            "company": "US Navy",
            "role": "organizer",
        },
    )
    assert resp.status_code == 201, resp.get_json()
    assert_matches_contract(
        "user-service", "POST", "/api/v1/users", _contract_response(resp)
    )


@pytest.mark.req("REQ-USR-E02")
def test_get_users_list_matches_contract(client):
    """GET /api/v1/users -> 200 conforms to the ``UserPage`` schema."""
    _create_user(client, email="one@example.com")
    _create_user(client, email="two@example.com")
    resp = client.get("/api/v1/users")
    assert resp.status_code == 200, resp.get_json()
    assert_matches_contract(
        "user-service", "GET", "/api/v1/users", _contract_response(resp)
    )


@pytest.mark.req("REQ-USR-E03")
def test_get_user_by_id_matches_contract(client):
    """GET /api/v1/users/{id} -> 200 conforms to the ``User`` schema."""
    user = _create_user(client)
    resp = client.get(f"/api/v1/users/{user['id']}")
    assert resp.status_code == 200, resp.get_json()
    assert_matches_contract(
        "user-service",
        "GET",
        f"/api/v1/users/{user['id']}",
        _contract_response(resp),
    )


@pytest.mark.req("REQ-USR-E04")
def test_put_user_matches_contract(client):
    """PUT /api/v1/users/{id} -> 200 conforms to the ``User`` schema."""
    user = _create_user(client)
    resp = client.put(
        f"/api/v1/users/{user['id']}",
        json={
            "first_name": "Ada",
            "last_name": "Byron",
            "email": "ada.byron@example.com",
            "role": "attendee",
        },
    )
    assert resp.status_code == 200, resp.get_json()
    assert_matches_contract(
        "user-service",
        "PUT",
        f"/api/v1/users/{user['id']}",
        _contract_response(resp),
    )


@pytest.mark.req("REQ-USR-E05")
def test_patch_user_matches_contract(client):
    """PATCH /api/v1/users/{id} -> 200 conforms to the ``User`` schema."""
    user = _create_user(client)
    resp = client.patch(
        f"/api/v1/users/{user['id']}",
        json={"company": "New Corp"},
    )
    assert resp.status_code == 200, resp.get_json()
    assert_matches_contract(
        "user-service",
        "PATCH",
        f"/api/v1/users/{user['id']}",
        _contract_response(resp),
    )


@pytest.mark.req("REQ-USR-E06")
def test_delete_user_matches_contract(client):
    """DELETE /api/v1/users/{id} -> 204 (no body) satisfies the contract."""
    user = _create_user(client)
    resp = client.delete(f"/api/v1/users/{user['id']}")
    assert resp.status_code == 204
    assert_matches_contract(
        "user-service",
        "DELETE",
        f"/api/v1/users/{user['id']}",
        _contract_response(resp),
    )


@pytest.mark.req("REQ-USR-E07")
def test_health_matches_contract(client):
    """GET /health -> 200 conforms to the ``Health`` schema."""
    resp = client.get("/health")
    assert resp.status_code == 200, resp.get_json()
    assert_matches_contract(
        "user-service", "GET", "/health", _contract_response(resp)
    )
