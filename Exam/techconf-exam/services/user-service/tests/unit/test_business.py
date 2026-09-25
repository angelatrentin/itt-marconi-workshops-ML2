"""
Unit tests for the domain logic in ``app.business``.

This module is shared across tasks: task 7.2 owns the ``create_user`` tests
(prefixed ``test_create_``) and task 8.2 owns the read/update/delete tests.
To avoid write collisions, keep additions clearly scoped and never delete
existing functions from another task.

Requirements: REQ-USR-B01, REQ-USR-B02, REQ-USR-F01
"""

import uuid

import pytest

from app.business import EmailAlreadyExists, create_user
from app.repository import MemoryUserRepository


# --- create_user tests (task 7.2) -----------------------------------------

REQUIRED_USER_FIELDS = (
    "id",
    "first_name",
    "last_name",
    "email",
    "company",
    "role",
    "created_at",
    "updated_at",
)


@pytest.mark.req("REQ-USR-F01")
def test_create_returns_all_required_fields():
    repo = MemoryUserRepository()
    result = create_user(
        repo,
        {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
            "company": "Analytical Engines",
            "role": "speaker",
        },
    )

    for field in REQUIRED_USER_FIELDS:
        assert field in result, f"missing field {field!r} in created user"

    assert result["first_name"] == "Ada"
    assert result["last_name"] == "Lovelace"
    assert result["email"] == "ada@example.com"
    assert result["company"] == "Analytical Engines"
    assert result["role"] == "speaker"


@pytest.mark.req("REQ-USR-B02")
def test_create_normalizes_email_to_lowercase():
    repo = MemoryUserRepository()
    result = create_user(
        repo,
        {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "Ada@Example.COM",
        },
    )

    assert result["email"] == "ada@example.com"
    # And it must be persisted lowercase, retrievable case-insensitively.
    assert repo.get_by_email("ADA@EXAMPLE.COM") is not None


@pytest.mark.req("REQ-USR-B01")
def test_create_duplicate_email_case_insensitive_raises():
    repo = MemoryUserRepository()
    create_user(
        repo,
        {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
        },
    )

    with pytest.raises(EmailAlreadyExists):
        create_user(
            repo,
            {
                "first_name": "Grace",
                "last_name": "Hopper",
                "email": "ADA@Example.Com",
            },
        )


@pytest.mark.req("REQ-USR-F01")
def test_create_role_defaults_to_attendee_when_absent():
    repo = MemoryUserRepository()
    result = create_user(
        repo,
        {
            "first_name": "Grace",
            "last_name": "Hopper",
            "email": "grace@example.com",
        },
    )

    assert result["role"] == "attendee"


@pytest.mark.req("REQ-USR-F01")
def test_create_company_defaults_to_none_when_absent():
    repo = MemoryUserRepository()
    result = create_user(
        repo,
        {
            "first_name": "Grace",
            "last_name": "Hopper",
            "email": "grace@example.com",
        },
    )

    assert result["company"] is None


@pytest.mark.req("REQ-USR-F01")
def test_create_id_is_valid_uuid_v4():
    repo = MemoryUserRepository()
    result = create_user(
        repo,
        {
            "first_name": "Alan",
            "last_name": "Turing",
            "email": "alan@example.com",
        },
    )

    parsed = uuid.UUID(result["id"])
    assert parsed.version == 4


@pytest.mark.req("REQ-USR-F01")
def test_create_timestamps_equal_and_iso8601_utc_z():
    repo = MemoryUserRepository()
    result = create_user(
        repo,
        {
            "first_name": "Alan",
            "last_name": "Turing",
            "email": "alan@example.com",
        },
    )

    created_at = result["created_at"]
    updated_at = result["updated_at"]

    # On creation both timestamps are identical.
    assert created_at == updated_at
    # ISO 8601 UTC ending with 'Z'.
    assert created_at.endswith("Z")
    # Parseable as an ISO 8601 UTC timestamp (swap 'Z' for the offset form).
    from datetime import datetime, timezone

    parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timezone.utc.utcoffset(None)

# --- read / update / delete tests (task 8.2) -------------------------------

from app.business import (  # noqa: E402  (grouped with task 8.2 additions)
    UserNotFound,
    delete_user,
    get_user,
    list_users,
    replace_user,
    update_user,
)


def _seed_user(
    repo,
    first_name="Ada",
    last_name="Lovelace",
    email="ada@example.com",
    company="Analytical Engines",
    role="attendee",
):
    """Create and return a user via ``create_user`` for use as test fixtures."""
    return create_user(
        repo,
        {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "company": company,
            "role": role,
        },
    )


# --- get_user --------------------------------------------------------------


def test_get_nonexistent_uuid_raises_user_not_found():
    repo = MemoryUserRepository()
    with pytest.raises(UserNotFound):
        get_user(repo, str(uuid.uuid4()))


def test_get_existing_returns_the_user():
    repo = MemoryUserRepository()
    created = _seed_user(repo)

    fetched = get_user(repo, created["id"])

    assert fetched == created


# --- list_users ------------------------------------------------------------


@pytest.mark.req("REQ-USR-B03")
def test_list_role_filter_returns_only_matching_role():
    repo = MemoryUserRepository()
    _seed_user(repo, email="attendee1@example.com", role="attendee")
    _seed_user(repo, email="attendee2@example.com", role="attendee")
    _seed_user(repo, email="speaker1@example.com", role="speaker")

    page = list_users(repo, role="speaker", email=None, page=1, page_size=10)

    assert page["total"] == 1
    assert len(page["items"]) == 1
    assert page["items"][0]["email"] == "speaker1@example.com"
    assert page["items"][0]["role"] == "speaker"


@pytest.mark.req("REQ-USR-B03")
def test_list_email_filter_is_case_insensitive():
    repo = MemoryUserRepository()
    _seed_user(repo, email="ada@example.com")
    _seed_user(repo, email="grace@example.com")

    page = list_users(
        repo, role=None, email="ADA@EXAMPLE.COM", page=1, page_size=10
    )

    assert page["total"] == 1
    assert len(page["items"]) == 1
    assert page["items"][0]["email"] == "ada@example.com"


@pytest.mark.req("REQ-USR-B03")
def test_list_combined_role_and_email_filters_are_anded():
    repo = MemoryUserRepository()
    _seed_user(repo, email="ada@example.com", role="speaker")
    _seed_user(repo, email="ada2@example.com", role="attendee")
    _seed_user(repo, email="grace@example.com", role="speaker")

    # Matches email but not role -> excluded.
    page = list_users(
        repo, role="attendee", email="ada@example.com", page=1, page_size=10
    )
    assert page["total"] == 0
    assert page["items"] == []

    # Matches both role and email -> included.
    page2 = list_users(
        repo, role="speaker", email="ada@example.com", page=1, page_size=10
    )
    assert page2["total"] == 1
    assert page2["items"][0]["email"] == "ada@example.com"
    assert page2["items"][0]["role"] == "speaker"


def test_list_pagination_totals_span_all_pages():
    repo = MemoryUserRepository()
    for i in range(5):
        _seed_user(repo, email=f"user{i}@example.com")

    page1 = list_users(repo, role=None, email=None, page=1, page_size=2)
    assert page1["total"] == 5
    assert page1["page"] == 1
    assert page1["page_size"] == 2
    assert len(page1["items"]) == 2

    page3 = list_users(repo, role=None, email=None, page=3, page_size=2)
    assert page3["total"] == 5
    assert len(page3["items"]) == 1  # last partial page


def test_list_page_beyond_last_is_empty_with_correct_total():
    repo = MemoryUserRepository()
    for i in range(3):
        _seed_user(repo, email=f"user{i}@example.com")

    page = list_users(repo, role=None, email=None, page=99, page_size=10)

    assert page["items"] == []
    assert page["total"] == 3
    assert page["page"] == 99
    assert page["page_size"] == 10


# --- replace_user ----------------------------------------------------------


def test_replace_updates_fields_and_bumps_updated_at_created_unchanged():
    repo = MemoryUserRepository()
    created = _seed_user(
        repo,
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        company="Old Co",
        role="attendee",
    )

    replaced = replace_user(
        repo,
        created["id"],
        {
            "first_name": "Augusta",
            "last_name": "King",
            "email": "augusta@example.com",
            "company": "New Co",
            "role": "speaker",
        },
    )

    assert replaced["first_name"] == "Augusta"
    assert replaced["last_name"] == "King"
    assert replaced["email"] == "augusta@example.com"
    assert replaced["company"] == "New Co"
    assert replaced["role"] == "speaker"
    # created_at unchanged; updated_at refreshed and moved forward.
    assert replaced["created_at"] == created["created_at"]
    assert replaced["updated_at"] >= created["updated_at"]
    # id is stable across a replace.
    assert replaced["id"] == created["id"]


def test_replace_defaults_company_none_and_role_attendee_when_omitted():
    repo = MemoryUserRepository()
    created = _seed_user(repo, company="Some Co", role="speaker")

    replaced = replace_user(
        repo,
        created["id"],
        {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
        },
    )

    assert replaced["company"] is None
    assert replaced["role"] == "attendee"


def test_replace_normalizes_email_to_lowercase():
    repo = MemoryUserRepository()
    created = _seed_user(repo)

    replaced = replace_user(
        repo,
        created["id"],
        {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "New.Email@EXAMPLE.com",
        },
    )

    assert replaced["email"] == "new.email@example.com"


def test_replace_nonexistent_raises_user_not_found():
    repo = MemoryUserRepository()
    with pytest.raises(UserNotFound):
        replace_user(
            repo,
            str(uuid.uuid4()),
            {
                "first_name": "Ada",
                "last_name": "Lovelace",
                "email": "ada@example.com",
            },
        )


@pytest.mark.req("REQ-USR-B01")
def test_replace_self_update_with_own_email_is_not_a_conflict():
    repo = MemoryUserRepository()
    created = _seed_user(repo, email="ada@example.com")

    replaced = replace_user(
        repo,
        created["id"],
        {
            "first_name": "Augusta",
            "last_name": "King",
            "email": "ada@example.com",  # own email, uppercased variant below
        },
    )

    assert replaced["email"] == "ada@example.com"
    assert replaced["first_name"] == "Augusta"


@pytest.mark.req("REQ-USR-B01")
def test_replace_self_update_with_own_email_case_insensitive_is_not_a_conflict():
    repo = MemoryUserRepository()
    created = _seed_user(repo, email="ada@example.com")

    replaced = replace_user(
        repo,
        created["id"],
        {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ADA@Example.COM",
        },
    )

    assert replaced["email"] == "ada@example.com"


@pytest.mark.req("REQ-USR-B01")
def test_replace_with_another_users_email_raises_email_already_exists():
    repo = MemoryUserRepository()
    _seed_user(repo, email="taken@example.com")
    target = _seed_user(repo, email="ada@example.com")

    with pytest.raises(EmailAlreadyExists):
        replace_user(
            repo,
            target["id"],
            {
                "first_name": "Ada",
                "last_name": "Lovelace",
                "email": "taken@example.com",
            },
        )


# --- update_user -----------------------------------------------------------


def test_update_partial_changes_only_provided_fields():
    repo = MemoryUserRepository()
    created = _seed_user(
        repo,
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        company="Analytical Engines",
        role="attendee",
    )

    updated = update_user(repo, created["id"], {"role": "speaker"})

    # Only role changed; everything else preserved.
    assert updated["role"] == "speaker"
    assert updated["first_name"] == "Ada"
    assert updated["last_name"] == "Lovelace"
    assert updated["email"] == "ada@example.com"
    assert updated["company"] == "Analytical Engines"
    assert updated["created_at"] == created["created_at"]
    assert updated["updated_at"] >= created["updated_at"]


def test_update_empty_body_returns_user_unchanged_and_updated_at_untouched():
    repo = MemoryUserRepository()
    created = _seed_user(repo)

    updated = update_user(repo, created["id"], {})

    assert updated == created
    assert updated["updated_at"] == created["updated_at"]


@pytest.mark.req("REQ-USR-B01")
def test_update_with_another_users_email_raises_email_already_exists():
    repo = MemoryUserRepository()
    _seed_user(repo, email="taken@example.com")
    target = _seed_user(repo, email="ada@example.com")

    with pytest.raises(EmailAlreadyExists):
        update_user(repo, target["id"], {"email": "taken@example.com"})


@pytest.mark.req("REQ-USR-B01")
def test_update_with_own_email_is_ok():
    repo = MemoryUserRepository()
    created = _seed_user(repo, email="ada@example.com")

    updated = update_user(repo, created["id"], {"email": "ADA@Example.com"})

    assert updated["email"] == "ada@example.com"


def test_update_nonexistent_raises_user_not_found():
    repo = MemoryUserRepository()
    with pytest.raises(UserNotFound):
        update_user(repo, str(uuid.uuid4()), {"role": "speaker"})


# --- delete_user -----------------------------------------------------------


@pytest.mark.req("REQ-USR-E05")
def test_delete_removes_the_user():
    repo = MemoryUserRepository()
    created = _seed_user(repo)

    delete_user(repo, created["id"])

    with pytest.raises(UserNotFound):
        get_user(repo, created["id"])


@pytest.mark.req("REQ-USR-E05")
def test_delete_second_call_raises_user_not_found():
    repo = MemoryUserRepository()
    created = _seed_user(repo)

    delete_user(repo, created["id"])

    with pytest.raises(UserNotFound):
        delete_user(repo, created["id"])
