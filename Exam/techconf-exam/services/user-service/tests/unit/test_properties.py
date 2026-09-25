"""
test_properties.py — Property-based tests (Hypothesis) for user-service.

Implements the 8 formal correctness properties from the design document.
Each property has @settings(max_examples=100) and carries the exact tracer
comment required by the task.

HTTP-level properties use the Flask test client built from a fresh
``create_app(MemoryUserRepository())`` per example (emails are globally unique
per app instance, so a fresh app avoids cross-example collision flakiness).
The backend-interchange property (Property 8) drives the repositories directly.

Requirements: REQ-USR-B01, REQ-USR-B02, REQ-USR-E02, REQ-USR-E03,
              REQ-USR-E06, REQ-USR-F01, REQ-USR-P03
"""

import shutil
import tempfile
import uuid
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.main import create_app
from app.repository import (
    JsonUserRepository,
    MemoryUserRepository,
    SqliteUserRepository,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------
# Names: letters/digits only (codepoints 65..122 covers A-Z, some punctuation,
# a-z), non-empty, bounded to the 1..50 length the validator accepts. Using a
# constrained alphabet keeps generated values inside the valid input space so
# the tests exercise real behaviour rather than validation rejections.
_name_strategy = st.text(
    alphabet=st.characters(min_codepoint=65, max_codepoint=122),
    min_size=1,
    max_size=50,
)

# Email local part: lowercase letters + digits, keeps the address valid for the
# service's email regex (single @, non-empty local/domain, dot in the domain).
_local_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
    min_size=1,
    max_size=10,
)

_role_strategy = st.sampled_from(["attendee", "speaker", "organizer"])


def _fresh_client():
    """Build a Flask test client backed by a fresh in-memory repository."""
    app = create_app(MemoryUserRepository())
    return app.test_client()


def _unique_email():
    """A globally-unique lowercase email, safe to reuse across examples."""
    return f"user-{uuid.uuid4().hex}@example.com"


def _randomize_case(text: str, seed: int) -> str:
    """Flip the case of characters deterministically from a seed integer."""
    chars = []
    for i, ch in enumerate(text):
        if (seed >> (i % 31)) & 1:
            chars.append(ch.upper())
        else:
            chars.append(ch.lower())
    return "".join(chars)


# ---------------------------------------------------------------------------
# Property 1 — round-trip creazione/lettura
# ---------------------------------------------------------------------------
@settings(max_examples=100)
@given(
    first_name=_name_strategy,
    last_name=_name_strategy,
    local=_local_strategy,
    role=_role_strategy,
)
def test_property_1_round_trip_create_read(first_name, last_name, local, role):
    # Feature: user-service, Property 1: round-trip creazione/lettura
    # Validates: REQ-USR-E01, REQ-USR-E03, REQ-USR-F01
    client = _fresh_client()
    email = f"{local}-{uuid.uuid4().hex}@example.com"
    payload = {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "role": role,
    }

    post = client.post("/api/v1/users", json=payload)
    assert post.status_code == 201, post.get_json()
    created = post.get_json()
    user_id = created["id"]

    get = client.get(f"/api/v1/users/{user_id}")
    assert get.status_code == 200
    fetched = get.get_json()

    required = (
        "id",
        "first_name",
        "last_name",
        "email",
        "role",
        "created_at",
        "updated_at",
    )
    for field in required:
        assert field in fetched, f"missing field {field}"

    assert fetched["id"] == user_id
    assert fetched["first_name"] == first_name
    assert fetched["last_name"] == last_name
    assert fetched["email"] == email.lower()
    assert fetched["role"] == role
    # created_at/updated_at are non-empty timestamps assigned by the server.
    assert fetched["created_at"]
    assert fetched["updated_at"]


# ---------------------------------------------------------------------------
# Property 2 — normalizzazione email invariante
# ---------------------------------------------------------------------------
@settings(max_examples=100)
@given(
    local=_local_strategy,
    domain=_local_strategy,
    case_seed=st.integers(min_value=0, max_value=2**31 - 1),
)
def test_property_2_email_normalization_invariant(local, domain, case_seed):
    # Feature: user-service, Property 2: normalizzazione email invariante
    # Validates: REQ-USR-B02
    client = _fresh_client()
    # Build an email with arbitrary case, then guarantee uniqueness via a
    # random suffix so repeated examples never collide.
    base = f"{local}-{uuid.uuid4().hex}@{domain}.com"
    email = _randomize_case(base, case_seed)

    resp = client.post(
        "/api/v1/users",
        json={
            "first_name": "Alice",
            "last_name": "Smith",
            "email": email,
        },
    )
    assert resp.status_code == 201, resp.get_json()
    assert resp.get_json()["email"] == email.lower()


# ---------------------------------------------------------------------------
# Property 3 — unicità email globale (case-insensitive)
# ---------------------------------------------------------------------------
@settings(max_examples=100)
@given(
    local=_local_strategy,
    domain=_local_strategy,
    case_seed=st.integers(min_value=0, max_value=2**31 - 1),
)
def test_property_3_email_uniqueness_global(local, domain, case_seed):
    # Feature: user-service, Property 3: unicità email globale
    # Validates: REQ-USR-B01
    client = _fresh_client()
    email = f"{local}-{uuid.uuid4().hex}@{domain}.com"

    first = client.post(
        "/api/v1/users",
        json={"first_name": "Alice", "last_name": "Smith", "email": email},
    )
    assert first.status_code == 201, first.get_json()

    # Second create with a different-case variant of the same email must 409.
    variant = _randomize_case(email, case_seed)
    second = client.post(
        "/api/v1/users",
        json={"first_name": "Bob", "last_name": "Jones", "email": variant},
    )
    assert second.status_code == 409
    assert second.get_json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"

    # No two users ever share a normalized email: exactly one user exists.
    listing = client.get("/api/v1/users?page_size=100").get_json()
    normalized = [u["email"].lower() for u in listing["items"]]
    assert len(normalized) == len(set(normalized))
    assert listing["total"] == 1


# ---------------------------------------------------------------------------
# Property 4 — UUID v4 generato lato server
# ---------------------------------------------------------------------------
@settings(max_examples=100)
@given(
    local=_local_strategy,
    supplied_id=st.uuids(version=4),
)
def test_property_4_uuid_v4_server_side(local, supplied_id):
    # Feature: user-service, Property 4: UUID v4 server-side
    # Validates: REQ-USR-F01.3, REQ-USR-F01.4
    client = _fresh_client()
    email = f"{local}-{uuid.uuid4().hex}@example.com"

    resp = client.post(
        "/api/v1/users",
        json={"first_name": "Alice", "last_name": "Smith", "email": email},
    )
    assert resp.status_code == 201, resp.get_json()
    returned_id = resp.get_json()["id"]
    assert uuid.UUID(returned_id).version == 4

    # A body that includes an `id` field must be rejected with 422.
    rejected = client.post(
        "/api/v1/users",
        json={
            "first_name": "Bob",
            "last_name": "Jones",
            "email": f"{local}-{uuid.uuid4().hex}@example.com",
            "id": str(supplied_id),
        },
    )
    assert rejected.status_code == 422
    assert rejected.get_json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Property 5 — consistenza paginazione
# ---------------------------------------------------------------------------
@settings(max_examples=100)
@given(
    n=st.integers(min_value=0, max_value=20),
    page_size=st.integers(min_value=1, max_value=100),
)
def test_property_5_pagination_consistency(n, page_size):
    # Feature: user-service, Property 5: consistenza paginazione
    # Validates: REQ-USR-E02
    client = _fresh_client()
    for _ in range(n):
        resp = client.post(
            "/api/v1/users",
            json={
                "first_name": "Alice",
                "last_name": "Smith",
                "email": _unique_email(),
            },
        )
        assert resp.status_code == 201, resp.get_json()

    # Page through every page; the summed item count must equal `total`.
    collected = 0
    total = None
    page = 1
    while True:
        body = client.get(
            f"/api/v1/users?page={page}&page_size={page_size}"
        ).get_json()
        if total is None:
            total = body["total"]
        else:
            assert body["total"] == total
        collected += len(body["items"])
        if len(body["items"]) == 0:
            break
        page += 1
        # Safety guard against an unexpected infinite loop.
        assert page <= n + 2

    assert total == n
    assert collected == total


# ---------------------------------------------------------------------------
# Property 6 — filtro per role
# ---------------------------------------------------------------------------
@settings(max_examples=100)
@given(roles=st.lists(_role_strategy, min_size=0, max_size=15))
def test_property_6_role_filter(roles):
    # Feature: user-service, Property 6: filtro per role
    # Validates: REQ-USR-B03.1
    client = _fresh_client()
    for role in roles:
        resp = client.post(
            "/api/v1/users",
            json={
                "first_name": "Alice",
                "last_name": "Smith",
                "email": _unique_email(),
                "role": role,
            },
        )
        assert resp.status_code == 201, resp.get_json()

    for role in ("attendee", "speaker", "organizer"):
        body = client.get(
            f"/api/v1/users?role={role}&page_size=100"
        ).get_json()
        for item in body["items"]:
            assert item["role"] == role
        assert body["total"] == roles.count(role)


# ---------------------------------------------------------------------------
# Property 7 — eliminazione rende l'id irraggiungibile
# ---------------------------------------------------------------------------
@settings(max_examples=100)
@given(local=_local_strategy)
def test_property_7_deletion_unreachable(local):
    # Feature: user-service, Property 7: eliminazione irraggiungibile
    # Validates: REQ-USR-E06
    client = _fresh_client()
    email = f"{local}-{uuid.uuid4().hex}@example.com"

    created = client.post(
        "/api/v1/users",
        json={"first_name": "Alice", "last_name": "Smith", "email": email},
    )
    assert created.status_code == 201, created.get_json()
    user_id = created.get_json()["id"]

    assert client.delete(f"/api/v1/users/{user_id}").status_code == 204

    # After deletion every method on the same id must return 404.
    assert client.get(f"/api/v1/users/{user_id}").status_code == 404
    assert client.put(
        f"/api/v1/users/{user_id}",
        json={"first_name": "A", "last_name": "B", "email": _unique_email()},
    ).status_code == 404
    assert client.patch(
        f"/api/v1/users/{user_id}", json={"first_name": "Changed"}
    ).status_code == 404
    assert client.delete(f"/api/v1/users/{user_id}").status_code == 404


# ---------------------------------------------------------------------------
# Property 8 — intercambiabilità backend
# ---------------------------------------------------------------------------
def _observable(user: dict) -> dict:
    """Project a stored user onto the fields that must match across backends.

    ``id``, ``created_at`` and ``updated_at`` are server-generated and differ
    between independent runs, so they are excluded from the comparison.
    """
    return {
        "first_name": user["first_name"],
        "last_name": user["last_name"],
        "email": user["email"],
        "company": user.get("company"),
        "role": user["role"],
    }


def _run_crud_sequence(repo):
    """Drive a fixed CRUD sequence against a repository and record results."""
    now = "2026-01-01T00:00:00Z"
    results = []

    # create two users
    u1 = repo.create(
        {
            "id": str(uuid.uuid4()),
            "first_name": "Alice",
            "last_name": "Smith",
            "email": "alice@example.com",
            "company": "Acme",
            "role": "speaker",
            "created_at": now,
            "updated_at": now,
        }
    )
    u2 = repo.create(
        {
            "id": str(uuid.uuid4()),
            "first_name": "Bob",
            "last_name": "Jones",
            "email": "bob@example.com",
            "company": None,
            "role": "attendee",
            "created_at": now,
            "updated_at": now,
        }
    )
    results.append(_observable(u1))
    results.append(_observable(u2))

    # get_by_id / get_by_email
    results.append(_observable(repo.get_by_id(u1["id"])))
    results.append(_observable(repo.get_by_email("bob@example.com")))
    results.append(repo.get_by_id("00000000-0000-4000-8000-000000000000"))

    # list total + role filter total
    _, total = repo.list_users(None, None, 1, 10)
    results.append(total)
    _, speaker_total = repo.list_users("speaker", None, 1, 10)
    results.append(speaker_total)

    # update u2, then read back
    repo.update(u2["id"], {"role": "organizer", "updated_at": now})
    results.append(_observable(repo.get_by_id(u2["id"])))

    # delete u1, then confirm gone and re-delete returns False
    results.append(repo.delete(u1["id"]))
    results.append(repo.get_by_id(u1["id"]))
    results.append(repo.delete(u1["id"]))

    # final total
    _, final_total = repo.list_users(None, None, 1, 10)
    results.append(final_total)

    return results


@settings(max_examples=100)
@given(dummy=st.integers(min_value=0, max_value=1000))
def test_property_8_backend_interchangeability(dummy):
    # Feature: user-service, Property 8: intercambiabilità backend
    # Validates: REQ-USR-P03
    json_dir = Path(tempfile.mkdtemp())
    sqlite_dir = Path(tempfile.mkdtemp())
    try:
        memory_results = _run_crud_sequence(MemoryUserRepository())
        json_results = _run_crud_sequence(JsonUserRepository(json_dir))
        sqlite_results = _run_crud_sequence(SqliteUserRepository(sqlite_dir))

        assert memory_results == json_results
        assert memory_results == sqlite_results
    finally:
        shutil.rmtree(json_dir, ignore_errors=True)
        shutil.rmtree(sqlite_dir, ignore_errors=True)
