"""
test_repository_sqlite.py — Unit tests for SqliteUserRepository

Uses the pytest ``tmp_path`` fixture to give every test a fresh, isolated
data directory so the SQLite database (``{tmp_path}/users.db``) never leaks
state across tests.

Covers the same CRUD surface as the in-memory repository plus a schema check
that verifies the ``users`` table is created with the expected columns.

Requirements: REQ-USR-P03.3, REQ-USR-P03.6
"""

import sqlite3

import pytest

from app.repository import SqliteUserRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_repo(tmp_path):
    """Build a fresh SqliteUserRepository rooted at the per-test tmp dir."""
    return SqliteUserRepository(tmp_path)


def _user(
    user_id: str,
    email: str,
    *,
    first_name: str = "Ada",
    last_name: str = "Lovelace",
    company: str | None = "TechConf",
    role: str = "attendee",
    created_at: str = "2024-01-01T00:00:00Z",
    updated_at: str = "2024-01-01T00:00:00Z",
) -> dict:
    """Produce a complete user dict as the business layer would pass it."""
    return {
        "id": user_id,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "company": company,
        "role": role,
        "created_at": created_at,
        "updated_at": updated_at,
    }


# ---------------------------------------------------------------------------
# Schema (REQ-USR-P03.3, REQ-USR-P03.6)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-P03")
def test_users_table_created_with_expected_columns(tmp_path):
    """Constructing the repo creates users.db with the expected columns."""
    _make_repo(tmp_path)

    db_path = tmp_path / "users.db"
    assert db_path.exists()

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("PRAGMA table_info(users)").fetchall()
    finally:
        conn.close()

    # rows are (cid, name, type, notnull, dflt_value, pk)
    column_names = [row[1] for row in rows]
    expected = [
        "id",
        "first_name",
        "last_name",
        "email",
        "company",
        "role",
        "created_at",
        "updated_at",
    ]
    assert column_names == expected


# ---------------------------------------------------------------------------
# create / get_by_id (REQ-USR-P03.1, REQ-USR-P03.3)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-P03")
def test_create_and_get_by_id(tmp_path):
    """A created user is retrievable by id with all fields intact."""
    repo = _make_repo(tmp_path)
    user = _user("u1", "ada@example.com")

    created = repo.create(user)
    assert created == user

    fetched = repo.get_by_id("u1")
    assert fetched == user


@pytest.mark.req("REQ-USR-P03")
def test_get_by_id_missing_returns_none(tmp_path):
    """get_by_id returns None for an unknown id."""
    repo = _make_repo(tmp_path)
    assert repo.get_by_id("does-not-exist") is None


# ---------------------------------------------------------------------------
# get_by_email — case-insensitive (REQ-USR-P03.3)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-P03")
def test_get_by_email_case_insensitive(tmp_path):
    """get_by_email matches regardless of the case of the query."""
    repo = _make_repo(tmp_path)
    repo.create(_user("u1", "ada@example.com"))

    assert repo.get_by_email("ada@example.com") is not None
    assert repo.get_by_email("ADA@EXAMPLE.COM") is not None
    assert repo.get_by_email("Ada@Example.Com")["id"] == "u1"


@pytest.mark.req("REQ-USR-P03")
def test_get_by_email_missing_returns_none(tmp_path):
    """get_by_email returns None when no user has that email."""
    repo = _make_repo(tmp_path)
    repo.create(_user("u1", "ada@example.com"))
    assert repo.get_by_email("nobody@example.com") is None


# ---------------------------------------------------------------------------
# list_users — filters + pagination (REQ-USR-P03.3)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-P03")
def test_list_users_no_filter_returns_all(tmp_path):
    """Without filters, list_users returns every user and the correct total."""
    repo = _make_repo(tmp_path)
    repo.create(_user("u1", "a@example.com", created_at="2024-01-01T00:00:00Z"))
    repo.create(_user("u2", "b@example.com", created_at="2024-01-02T00:00:00Z"))

    items, total = repo.list_users(None, None, 1, 20)
    assert total == 2
    assert {item["id"] for item in items} == {"u1", "u2"}


@pytest.mark.req("REQ-USR-P03")
def test_list_users_role_filter(tmp_path):
    """The role filter keeps only users with the exact matching role."""
    repo = _make_repo(tmp_path)
    repo.create(_user("u1", "a@example.com", role="attendee"))
    repo.create(_user("u2", "b@example.com", role="speaker"))
    repo.create(_user("u3", "c@example.com", role="speaker"))

    items, total = repo.list_users("speaker", None, 1, 20)
    assert total == 2
    assert all(item["role"] == "speaker" for item in items)
    assert {item["id"] for item in items} == {"u2", "u3"}


@pytest.mark.req("REQ-USR-P03")
def test_list_users_email_filter_case_insensitive(tmp_path):
    """The email filter is normalized to lowercase before matching."""
    repo = _make_repo(tmp_path)
    repo.create(_user("u1", "ada@example.com"))
    repo.create(_user("u2", "grace@example.com"))

    items, total = repo.list_users(None, "ADA@EXAMPLE.COM", 1, 20)
    assert total == 1
    assert items[0]["id"] == "u1"


@pytest.mark.req("REQ-USR-P03")
def test_list_users_pagination(tmp_path):
    """Pagination returns the correct slice while total counts every match."""
    repo = _make_repo(tmp_path)
    for i in range(5):
        repo.create(
            _user(
                f"u{i}",
                f"user{i}@example.com",
                created_at=f"2024-01-0{i + 1}T00:00:00Z",
            )
        )

    page1, total = repo.list_users(None, None, 1, 2)
    assert total == 5
    assert len(page1) == 2

    page3, total = repo.list_users(None, None, 3, 2)
    assert total == 5
    assert len(page3) == 1  # 5 items, last page holds the remainder

    # Ordering is by created_at, id, so pages do not overlap and cover all ids.
    seen = {u["id"] for u in page1}
    page2, _ = repo.list_users(None, None, 2, 2)
    seen |= {u["id"] for u in page2}
    seen |= {u["id"] for u in page3}
    assert seen == {"u0", "u1", "u2", "u3", "u4"}


@pytest.mark.req("REQ-USR-P03")
def test_list_users_page_beyond_last_is_empty(tmp_path):
    """A page past the end yields no items but the correct total."""
    repo = _make_repo(tmp_path)
    repo.create(_user("u1", "a@example.com"))

    items, total = repo.list_users(None, None, 5, 20)
    assert total == 1
    assert items == []


# ---------------------------------------------------------------------------
# update (REQ-USR-P03.3)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-P03")
def test_update_existing_user(tmp_path):
    """update applies the given fields and returns the updated record."""
    repo = _make_repo(tmp_path)
    repo.create(_user("u1", "ada@example.com", first_name="Ada"))

    updated = repo.update(
        "u1",
        {"first_name": "Grace", "updated_at": "2024-02-02T00:00:00Z"},
    )
    assert updated["first_name"] == "Grace"
    assert updated["updated_at"] == "2024-02-02T00:00:00Z"
    # Untouched fields are preserved.
    assert updated["email"] == "ada@example.com"
    assert repo.get_by_id("u1")["first_name"] == "Grace"


@pytest.mark.req("REQ-USR-P03")
def test_update_missing_returns_none(tmp_path):
    """update returns None when the user does not exist."""
    repo = _make_repo(tmp_path)
    assert repo.update("missing", {"first_name": "Grace"}) is None


# ---------------------------------------------------------------------------
# delete (REQ-USR-P03.3)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-P03")
def test_delete_then_second_delete(tmp_path):
    """delete returns True the first time and False on a repeat."""
    repo = _make_repo(tmp_path)
    repo.create(_user("u1", "ada@example.com"))

    assert repo.delete("u1") is True
    assert repo.delete("u1") is False


@pytest.mark.req("REQ-USR-P03")
def test_get_by_id_none_after_delete(tmp_path):
    """After delete, the user is no longer retrievable by id."""
    repo = _make_repo(tmp_path)
    repo.create(_user("u1", "ada@example.com"))
    repo.delete("u1")
    assert repo.get_by_id("u1") is None
