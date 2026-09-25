"""
test_repository_json.py — Unit tests for JsonUserRepository.

Mirrors the CRUD coverage of the in-memory repository and additionally
verifies the file-backed behaviour specific to the JSON implementation:
the ``users.json`` data file is auto-created when absent, and no stray
``users.json.tmp`` temporary file is left behind after a write.

Each test gets a fresh temporary directory via the pytest ``tmp_path``
fixture, so backends never share state.

Requirements: REQ-USR-P03.2
"""

import pytest

from app.repository import JsonUserRepository


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_user(
    user_id: str,
    email: str,
    role: str = "attendee",
    first_name: str = "Ada",
    last_name: str = "Lovelace",
    company: str | None = "TechConf",
) -> dict:
    """Build a complete user dict as the business layer would hand it over."""
    return {
        "id": user_id,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "company": company,
        "role": role,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }


@pytest.fixture()
def repo(tmp_path):
    """A fresh JsonUserRepository rooted in an isolated temp directory."""
    return JsonUserRepository(tmp_path)


# ---------------------------------------------------------------------------
# File bootstrap behaviour (REQ-USR-P03.2)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-P03")
def test_users_json_auto_created_when_absent(tmp_path):
    """Constructing the repo creates users.json even in an empty directory."""
    data_file = tmp_path / "users.json"
    assert not data_file.exists()

    JsonUserRepository(tmp_path)

    assert data_file.exists()


@pytest.mark.req("REQ-USR-P03")
def test_data_dir_auto_created_when_absent(tmp_path):
    """A missing DATA_DIR is created automatically on construction."""
    nested = tmp_path / "does" / "not" / "exist"
    assert not nested.exists()

    JsonUserRepository(nested)

    assert nested.exists()
    assert (nested / "users.json").exists()


@pytest.mark.req("REQ-USR-P03")
def test_no_leftover_tmp_file_after_write(repo, tmp_path):
    """After a write operation, the users.json.tmp scratch file is gone."""
    repo.create(_make_user("11111111-1111-4111-8111-111111111111", "a@x.com"))

    tmp_file = tmp_path / "users.json.tmp"
    assert not tmp_file.exists()
    # The definitive file is present and holds the committed data.
    assert (tmp_path / "users.json").exists()


# ---------------------------------------------------------------------------
# create / get_by_id (REQ-USR-P03.2)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-P03")
def test_create_and_get_by_id(repo):
    """A created user is retrievable by its id with identical fields."""
    user = _make_user("11111111-1111-4111-8111-111111111111", "ada@x.com")
    created = repo.create(user)
    assert created == user

    fetched = repo.get_by_id("11111111-1111-4111-8111-111111111111")
    assert fetched == user


@pytest.mark.req("REQ-USR-P03")
def test_get_by_id_missing_returns_none(repo):
    """An unknown id yields None."""
    assert repo.get_by_id("00000000-0000-4000-8000-000000000000") is None


@pytest.mark.req("REQ-USR-P03")
def test_create_persists_across_instances(tmp_path):
    """Data written by one instance is visible to a fresh instance (on disk)."""
    first = JsonUserRepository(tmp_path)
    first.create(_make_user("22222222-2222-4222-8222-222222222222", "b@x.com"))

    second = JsonUserRepository(tmp_path)
    assert second.get_by_id("22222222-2222-4222-8222-222222222222") is not None


# ---------------------------------------------------------------------------
# get_by_email (case-insensitive) (REQ-USR-P03.2)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-P03")
def test_get_by_email_case_insensitive(repo):
    """Lookup by email ignores case on the query side."""
    repo.create(_make_user("33333333-3333-4333-8333-333333333333", "user@example.com"))

    assert repo.get_by_email("user@example.com") is not None
    assert repo.get_by_email("USER@EXAMPLE.COM") is not None
    assert repo.get_by_email("User@Example.Com") is not None


@pytest.mark.req("REQ-USR-P03")
def test_get_by_email_missing_returns_none(repo):
    """An email with no matching user yields None."""
    assert repo.get_by_email("nobody@example.com") is None


# ---------------------------------------------------------------------------
# list_users — filters and pagination (REQ-USR-P03.2)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-P03")
def test_list_users_no_filters_returns_all(repo):
    """With no filters, total counts every user."""
    repo.create(_make_user("a1111111-1111-4111-8111-111111111111", "a@x.com"))
    repo.create(_make_user("a2222222-2222-4222-8222-222222222222", "b@x.com"))

    items, total = repo.list_users(role=None, email=None, page=1, page_size=10)
    assert total == 2
    assert len(items) == 2


@pytest.mark.req("REQ-USR-P03")
def test_list_users_role_filter(repo):
    """Filtering by role keeps only users with that exact role."""
    repo.create(_make_user("a1111111-1111-4111-8111-111111111111", "a@x.com", role="attendee"))
    repo.create(_make_user("a2222222-2222-4222-8222-222222222222", "b@x.com", role="speaker"))
    repo.create(_make_user("a3333333-3333-4333-8333-333333333333", "c@x.com", role="speaker"))

    items, total = repo.list_users(role="speaker", email=None, page=1, page_size=10)
    assert total == 2
    assert all(u["role"] == "speaker" for u in items)


@pytest.mark.req("REQ-USR-P03")
def test_list_users_email_filter_case_insensitive(repo):
    """The email filter matches case-insensitively."""
    repo.create(_make_user("a1111111-1111-4111-8111-111111111111", "match@x.com"))
    repo.create(_make_user("a2222222-2222-4222-8222-222222222222", "other@x.com"))

    items, total = repo.list_users(role=None, email="MATCH@X.COM", page=1, page_size=10)
    assert total == 1
    assert items[0]["email"] == "match@x.com"


@pytest.mark.req("REQ-USR-P03")
def test_list_users_pagination(repo):
    """Pagination slices the matched set while total stays global."""
    for i in range(5):
        repo.create(_make_user(f"a{i}111111-1111-4111-8111-111111111111", f"u{i}@x.com"))

    page1, total1 = repo.list_users(role=None, email=None, page=1, page_size=2)
    page2, total2 = repo.list_users(role=None, email=None, page=2, page_size=2)
    page3, total3 = repo.list_users(role=None, email=None, page=3, page_size=2)

    assert total1 == total2 == total3 == 5
    assert len(page1) == 2
    assert len(page2) == 2
    assert len(page3) == 1


@pytest.mark.req("REQ-USR-P03")
def test_list_users_page_beyond_end_is_empty(repo):
    """A page past the last one returns no items but the correct total."""
    repo.create(_make_user("a1111111-1111-4111-8111-111111111111", "a@x.com"))

    items, total = repo.list_users(role=None, email=None, page=5, page_size=10)
    assert items == []
    assert total == 1


# ---------------------------------------------------------------------------
# update (REQ-USR-P03.2)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-P03")
def test_update_existing_user(repo):
    """Update applies the given fields and returns the updated dict."""
    repo.create(_make_user("a1111111-1111-4111-8111-111111111111", "a@x.com"))

    updated = repo.update(
        "a1111111-1111-4111-8111-111111111111",
        {"first_name": "Grace", "updated_at": "2024-02-02T00:00:00Z"},
    )
    assert updated is not None
    assert updated["first_name"] == "Grace"
    assert updated["updated_at"] == "2024-02-02T00:00:00Z"

    # Change is persisted, not just returned.
    fetched = repo.get_by_id("a1111111-1111-4111-8111-111111111111")
    assert fetched["first_name"] == "Grace"


@pytest.mark.req("REQ-USR-P03")
def test_update_missing_user_returns_none(repo):
    """Updating an unknown id returns None."""
    assert repo.update("00000000-0000-4000-8000-000000000000", {"first_name": "X"}) is None


# ---------------------------------------------------------------------------
# delete (True then False, get_by_id None after) (REQ-USR-P03.2)
# ---------------------------------------------------------------------------

@pytest.mark.req("REQ-USR-P03")
def test_delete_returns_true_then_false(repo):
    """First delete returns True; deleting the same id again returns False."""
    repo.create(_make_user("a1111111-1111-4111-8111-111111111111", "a@x.com"))

    assert repo.delete("a1111111-1111-4111-8111-111111111111") is True
    assert repo.delete("a1111111-1111-4111-8111-111111111111") is False


@pytest.mark.req("REQ-USR-P03")
def test_get_by_id_none_after_delete(repo):
    """After deletion the user is no longer retrievable."""
    repo.create(_make_user("a1111111-1111-4111-8111-111111111111", "a@x.com"))
    repo.delete("a1111111-1111-4111-8111-111111111111")

    assert repo.get_by_id("a1111111-1111-4111-8111-111111111111") is None
