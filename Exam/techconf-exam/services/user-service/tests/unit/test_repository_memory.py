"""
Unit tests for MemoryUserRepository.

Covers the full CRUD surface of the in-memory backend: create/read, email
lookup (case-insensitive), listing with role/email filters and pagination,
update semantics and delete semantics.

Requirements: REQ-USR-P03.1
"""

import pytest

from app.repository import MemoryUserRepository


def _make_user(
    user_id: str,
    email: str,
    role: str = "attendee",
    first_name: str = "Ada",
    last_name: str = "Lovelace",
    company: str | None = "TechConf",
) -> dict:
    """Build a complete user dict as the business layer would pass it in."""
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


@pytest.fixture
def repo() -> MemoryUserRepository:
    """A fresh, empty repository for each test."""
    return MemoryUserRepository()


@pytest.mark.req("REQ-USR-P03")
def test_create_then_get_by_id_returns_stored_user(repo):
    user = _make_user("11111111-1111-4111-8111-111111111111", "ada@example.com")

    created = repo.create(user)
    assert created == user

    fetched = repo.get_by_id("11111111-1111-4111-8111-111111111111")
    assert fetched == user


@pytest.mark.req("REQ-USR-P03")
def test_get_by_id_missing_returns_none(repo):
    assert repo.get_by_id("does-not-exist") is None


@pytest.mark.req("REQ-USR-P03")
def test_create_returns_copy_not_live_reference(repo):
    user = _make_user(
        "22222222-2222-4222-8222-222222222222", "grace@example.com", first_name="Grace"
    )
    created = repo.create(user)

    # Mutating the returned dict must not affect stored state.
    created["first_name"] = "Mutated"
    fetched = repo.get_by_id("22222222-2222-4222-8222-222222222222")
    assert fetched["first_name"] == "Grace"


@pytest.mark.req("REQ-USR-P03")
def test_get_by_email_is_case_insensitive(repo):
    repo.create(_make_user("33333333-3333-4333-8333-333333333333", "mixed@example.com"))

    # Stored email is lowercase; lookup with different casing must still match.
    found = repo.get_by_email("MIXED@EXAMPLE.COM")
    assert found is not None
    assert found["email"] == "mixed@example.com"


@pytest.mark.req("REQ-USR-P03")
def test_get_by_email_missing_returns_none(repo):
    repo.create(_make_user("44444444-4444-4444-8444-444444444444", "known@example.com"))
    assert repo.get_by_email("unknown@example.com") is None


@pytest.mark.req("REQ-USR-P03")
def test_list_users_filter_by_role(repo):
    repo.create(_make_user("a1", "a@example.com", role="attendee"))
    repo.create(_make_user("s1", "s@example.com", role="speaker"))
    repo.create(_make_user("a2", "b@example.com", role="attendee"))

    items, total = repo.list_users(role="attendee", email=None, page=1, page_size=20)

    assert total == 2
    assert {u["id"] for u in items} == {"a1", "a2"}
    assert all(u["role"] == "attendee" for u in items)


@pytest.mark.req("REQ-USR-P03")
def test_list_users_filter_by_email_case_insensitive(repo):
    repo.create(_make_user("e1", "target@example.com"))
    repo.create(_make_user("e2", "other@example.com"))

    items, total = repo.list_users(
        role=None, email="TARGET@EXAMPLE.COM", page=1, page_size=20
    )

    assert total == 1
    assert items[0]["id"] == "e1"


@pytest.mark.req("REQ-USR-P03")
def test_list_users_combined_role_and_email_filter(repo):
    repo.create(_make_user("c1", "dup@example.com", role="attendee"))
    repo.create(_make_user("c2", "dup@example.com", role="speaker"))

    # Same email but only one matches the role too (AND semantics).
    items, total = repo.list_users(
        role="speaker", email="dup@example.com", page=1, page_size=20
    )

    assert total == 1
    assert items[0]["id"] == "c2"


@pytest.mark.req("REQ-USR-P03")
def test_list_users_pagination_total_across_pages(repo):
    for i in range(5):
        repo.create(_make_user(f"p{i}", f"p{i}@example.com"))

    page1, total1 = repo.list_users(role=None, email=None, page=1, page_size=2)
    page2, total2 = repo.list_users(role=None, email=None, page=2, page_size=2)
    page3, total3 = repo.list_users(role=None, email=None, page=3, page_size=2)

    # total is constant across pages and equal to the full match count.
    assert total1 == total2 == total3 == 5
    assert len(page1) == 2
    assert len(page2) == 2
    assert len(page3) == 1

    # Pages are disjoint and together cover every user.
    ids = {u["id"] for u in page1 + page2 + page3}
    assert ids == {f"p{i}" for i in range(5)}


@pytest.mark.req("REQ-USR-P03")
def test_list_users_page_beyond_last_returns_empty_items(repo):
    for i in range(3):
        repo.create(_make_user(f"b{i}", f"b{i}@example.com"))

    items, total = repo.list_users(role=None, email=None, page=99, page_size=10)

    assert items == []
    assert total == 3


@pytest.mark.req("REQ-USR-P03")
def test_update_modifies_fields_and_returns_updated_dict(repo):
    repo.create(_make_user("u1", "before@example.com", first_name="Before"))

    updated = repo.update("u1", {"first_name": "After", "company": "NewCo"})

    assert updated is not None
    assert updated["first_name"] == "After"
    assert updated["company"] == "NewCo"
    # Unchanged fields are preserved.
    assert updated["email"] == "before@example.com"

    # The change is persisted.
    fetched = repo.get_by_id("u1")
    assert fetched["first_name"] == "After"
    assert fetched["company"] == "NewCo"


@pytest.mark.req("REQ-USR-P03")
def test_update_missing_id_returns_none(repo):
    assert repo.update("missing", {"first_name": "Nope"}) is None


@pytest.mark.req("REQ-USR-P03")
def test_delete_returns_true_then_false(repo):
    repo.create(_make_user("d1", "delete@example.com"))

    assert repo.delete("d1") is True
    # Second delete on the same id: nothing to remove.
    assert repo.delete("d1") is False


@pytest.mark.req("REQ-USR-P03")
def test_get_by_id_returns_none_after_delete(repo):
    repo.create(_make_user("d2", "gone@example.com"))
    assert repo.get_by_id("d2") is not None

    repo.delete("d2")

    assert repo.get_by_id("d2") is None
