"""
test_user_api.py — Integration tests for the user-service HTTP layer.

These tests exercise the full stack (routes -> business -> repository) through
the Flask test client, using a fresh in-memory repository per test so that no
state leaks between cases. They cover the end-to-end behaviour of every
endpoint (IT-U01 .. IT-U08).

The app is built via ``create_app(MemoryUserRepository())`` — ``create_app``
takes the repository as an argument, so we inject a brand-new memory backend on
each test through the ``client`` fixture.

Requirements: REQ-USR-E01–E08, REQ-USR-B01–B03, REQ-USR-F01–F02
"""

import time
import uuid

import pytest

from app.main import create_app
from app.repository import MemoryUserRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def client():
    """Return a Flask test client backed by a fresh in-memory repository."""
    app = create_app(MemoryUserRepository())
    app.testing = True
    return app.test_client()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_REQUIRED_USER_FIELDS = (
    "id",
    "first_name",
    "last_name",
    "email",
    "role",
    "created_at",
    "updated_at",
)


def _valid_user_body(**overrides):
    """Return a valid UserCreate body, optionally overriding fields."""
    body = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@x.com",
        "company": "Analytical Engines",
        "role": "speaker",
    }
    body.update(overrides)
    return body


def _create_user(client, **overrides):
    """Create a user via the API and return the parsed response body."""
    resp = client.post("/api/v1/users", json=_valid_user_body(**overrides))
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


# ---------------------------------------------------------------------------
# IT-U01 — POST valid body -> 201, Location header, full User body
# ---------------------------------------------------------------------------
@pytest.mark.req("REQ-USR-E01")
@pytest.mark.req("REQ-USR-F01")
def test_it_u01_create_user_returns_201_with_location_and_user_body(client):
    resp = client.post("/api/v1/users", json=_valid_user_body())

    assert resp.status_code == 201
    body = resp.get_json()

    # All required User fields present.
    for field in _REQUIRED_USER_FIELDS:
        assert field in body, f"missing field {field!r}"

    # Location header points at the created resource.
    assert resp.headers.get("Location") == f"/api/v1/users/{body['id']}"

    # The id is a server-generated UUID; email normalized to lowercase.
    assert uuid.UUID(body["id"]).version == 4
    assert body["email"] == "ada@x.com"
    assert body["role"] == "speaker"
    # company may be present (here a string) — the schema allows null too.
    assert "company" in body


@pytest.mark.req("REQ-USR-F01")
def test_it_u01_company_defaults_to_null_when_omitted(client):
    # Omit company and role entirely to exercise the defaults.
    resp = client.post(
        "/api/v1/users",
        json={"first_name": "Grace", "last_name": "Hopper", "email": "grace@x.com"},
    )
    assert resp.status_code == 201
    created = resp.get_json()
    assert created["company"] is None
    # default role when omitted is attendee.
    assert created["role"] == "attendee"


# ---------------------------------------------------------------------------
# IT-U02 — POST missing required field -> 422 VALIDATION_ERROR
# ---------------------------------------------------------------------------
@pytest.mark.req("REQ-USR-E01")
@pytest.mark.req("REQ-USR-F02")
def test_it_u02_missing_required_field_returns_422(client):
    body = _valid_user_body()
    del body["email"]

    resp = client.post("/api/v1/users", json=body)

    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# IT-U03 — POST duplicate email (case-insensitive) -> 409 EMAIL_ALREADY_EXISTS
# ---------------------------------------------------------------------------
@pytest.mark.req("REQ-USR-B01")
@pytest.mark.req("REQ-USR-B02")
def test_it_u03_duplicate_email_case_insensitive_returns_409(client):
    first = client.post("/api/v1/users", json=_valid_user_body(email="ada@x.com"))
    assert first.status_code == 201

    dup = client.post("/api/v1/users", json=_valid_user_body(email="ADA@X.com"))

    assert dup.status_code == 409
    assert dup.get_json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


# ---------------------------------------------------------------------------
# IT-U04 — GET by id: existing -> 200; unknown valid UUID -> 404 NOT_FOUND
# ---------------------------------------------------------------------------
@pytest.mark.req("REQ-USR-E03")
def test_it_u04_get_existing_user_returns_200(client):
    created = _create_user(client)

    resp = client.get(f"/api/v1/users/{created['id']}")

    assert resp.status_code == 200
    assert resp.get_json()["id"] == created["id"]


@pytest.mark.req("REQ-USR-E03")
def test_it_u04_get_unknown_uuid_returns_404(client):
    unknown = str(uuid.uuid4())

    resp = client.get(f"/api/v1/users/{unknown}")

    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# IT-U05 — GET list paginated + role filter
# ---------------------------------------------------------------------------
@pytest.mark.req("REQ-USR-E02")
@pytest.mark.req("REQ-USR-B03")
def test_it_u05_list_pagination_metadata(client):
    # Create 5 users with distinct emails.
    for i in range(5):
        _create_user(client, email=f"user{i}@x.com", role="attendee")

    resp = client.get("/api/v1/users?page=1&page_size=2")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert body["total"] == 5
    assert len(body["items"]) == 2


@pytest.mark.req("REQ-USR-E02")
@pytest.mark.req("REQ-USR-B03")
def test_it_u05_list_role_filter_returns_only_speakers(client):
    _create_user(client, email="sp1@x.com", role="speaker")
    _create_user(client, email="sp2@x.com", role="speaker")
    _create_user(client, email="att1@x.com", role="attendee")
    _create_user(client, email="org1@x.com", role="organizer")

    resp = client.get("/api/v1/users?role=speaker")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 2
    assert all(item["role"] == "speaker" for item in body["items"])


# ---------------------------------------------------------------------------
# IT-U06 — PUT then PATCH -> 200 updated_at changed; PATCH {} -> unchanged
# ---------------------------------------------------------------------------
@pytest.mark.req("REQ-USR-E04")
@pytest.mark.req("REQ-USR-E05")
def test_it_u06_put_updates_user_and_bumps_updated_at(client):
    created = _create_user(client, email="put@x.com")
    original_updated_at = created["updated_at"]

    # Timestamps have second precision; cross a second boundary so the change
    # is observable.
    time.sleep(1.1)

    put_body = {
        "first_name": "Adeline",
        "last_name": "Byron",
        "email": "put@x.com",  # self-update, not a conflict
        "role": "organizer",
    }
    resp = client.put(f"/api/v1/users/{created['id']}", json=put_body)

    assert resp.status_code == 200
    updated = resp.get_json()
    assert updated["first_name"] == "Adeline"
    assert updated["role"] == "organizer"
    # company omitted on PUT defaults to null.
    assert updated["company"] is None
    assert updated["updated_at"] != original_updated_at
    # created_at is preserved.
    assert updated["created_at"] == created["created_at"]


@pytest.mark.req("REQ-USR-E05")
def test_it_u06_patch_updates_user_and_bumps_updated_at(client):
    created = _create_user(client, email="patch@x.com")
    original_updated_at = created["updated_at"]

    time.sleep(1.1)

    resp = client.patch(
        f"/api/v1/users/{created['id']}", json={"first_name": "Patched"}
    )

    assert resp.status_code == 200
    updated = resp.get_json()
    assert updated["first_name"] == "Patched"
    assert updated["updated_at"] != original_updated_at


@pytest.mark.req("REQ-USR-E05")
def test_it_u06_patch_empty_body_leaves_user_unchanged(client):
    created = _create_user(client, email="noop@x.com")

    time.sleep(1.1)

    resp = client.patch(f"/api/v1/users/{created['id']}", json={})

    assert resp.status_code == 200
    updated = resp.get_json()
    # updated_at is NOT bumped for an empty PATCH body.
    assert updated["updated_at"] == created["updated_at"]
    assert updated == created


# ---------------------------------------------------------------------------
# IT-U07 — DELETE -> 204; subsequent GET -> 404
# ---------------------------------------------------------------------------
@pytest.mark.req("REQ-USR-E06")
def test_it_u07_delete_then_get_returns_404(client):
    created = _create_user(client, email="del@x.com")

    delete_resp = client.delete(f"/api/v1/users/{created['id']}")
    assert delete_resp.status_code == 204
    assert delete_resp.get_data() == b""

    get_resp = client.get(f"/api/v1/users/{created['id']}")
    assert get_resp.status_code == 404
    assert get_resp.get_json()["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# IT-U08 — malformed JSON -> 400 MALFORMED_JSON; GET /health -> 200 Health
# ---------------------------------------------------------------------------
@pytest.mark.req("REQ-USR-E01")
def test_it_u08_malformed_json_returns_400(client):
    resp = client.post(
        "/api/v1/users", data="{not json", content_type="application/json"
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "MALFORMED_JSON"


@pytest.mark.req("REQ-USR-E07")
def test_it_u08_health_endpoint_returns_ok(client):
    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok", "service": "user-service"}
