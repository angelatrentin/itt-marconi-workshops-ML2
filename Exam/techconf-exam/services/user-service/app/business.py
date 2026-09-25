"""
business.py — Domain logic layer for user-service.

Contains all the business rules of the service (email normalization, global
case-insensitive email uniqueness, server-side UUID generation, timestamp
management). This module depends **only** on the
:class:`~app.repository.AbstractUserRepository` interface, which is injected via
the ``repo`` parameter (dependency injection). It has no knowledge of the HTTP
protocol.

This module must NOT import Flask: it is a pure domain layer. Input validation
(field types, lengths, required fields, ``additionalProperties: false``) is the
responsibility of ``routes.py``; here we only enforce domain rules.

Requirements: REQ-USR-B01, REQ-USR-B02, REQ-USR-F01, REQ-USR-F02
"""

import uuid
from datetime import datetime, timezone


class UserNotFound(Exception):
    """
    Raised when an operation targets a user UUID that does not exist.

    Translated by ``routes.py`` into a ``404 NOT_FOUND`` HTTP response.
    """


class EmailAlreadyExists(Exception):
    """
    Raised when a create/update would result in a duplicate email.

    The comparison is case-insensitive (both sides normalized to lowercase),
    so ``user@example.com`` and ``USER@EXAMPLE.COM`` collide. Translated by
    ``routes.py`` into a ``409 EMAIL_ALREADY_EXISTS`` HTTP response
    (Requirements: REQ-USR-B01).
    """


def _now_iso8601_utc() -> str:
    """
    Return the current UTC time as an ISO 8601 string with a trailing ``Z``.

    Produces timestamps in the shape ``2026-10-15T09:30:00Z`` (second
    precision, no microseconds) used for ``created_at``/``updated_at``
    (Requirements: REQ-USR-F01.5).
    """
    now = datetime.now(timezone.utc).replace(microsecond=0)
    # ``isoformat`` yields a ``+00:00`` offset; normalize it to the ``Z`` suffix
    # required by the contract.
    return now.isoformat().replace("+00:00", "Z")


def create_user(repo, data: dict) -> dict:
    """
    Create a new user, enforcing the service's domain rules.

    The input ``data`` is assumed to already have passed the structural
    validation performed by ``routes.py`` (required fields present, correct
    types and lengths, no forbidden ``id`` field). This function applies the
    domain rules:

    - normalizes ``email`` to lowercase (Requirements: REQ-USR-B02.1);
    - enforces global case-insensitive email uniqueness via
      :meth:`repo.get_by_email`, raising :class:`EmailAlreadyExists` on
      conflict (Requirements: REQ-USR-B01.1);
    - generates the ``id`` server-side as a UUID v4 string
      (Requirements: REQ-USR-F01.3);
    - defaults ``role`` to ``"attendee"`` when absent
      (Requirements: REQ-USR-F02.6);
    - defaults ``company`` to ``None`` when absent (Requirements: REQ-USR-F01.2);
    - sets both ``created_at`` and ``updated_at`` to the current ISO 8601 UTC
      timestamp (Requirements: REQ-USR-F01.5).

    Parameters
    ----------
    repo : AbstractUserRepository
        The persistence backend, injected by the caller.
    data : dict
        Validated user creation payload. May contain ``first_name``,
        ``last_name``, ``email``, and optionally ``company`` and ``role``.

    Returns
    -------
    dict
        The complete stored user dict as returned by the repository, with the
        keys: ``id``, ``first_name``, ``last_name``, ``email``, ``company``,
        ``role``, ``created_at``, ``updated_at``.

    Raises
    ------
    EmailAlreadyExists
        If an existing user already has the same normalized email.
    """
    # Normalize the email to lowercase before any comparison or persistence.
    normalized_email = data["email"].lower()

    # Enforce global, case-insensitive email uniqueness. The repository also
    # normalizes defensively, but we pass the already-normalized value.
    if repo.get_by_email(normalized_email) is not None:
        raise EmailAlreadyExists(normalized_email)

    # Timestamps: created_at and updated_at start identical on creation.
    timestamp = _now_iso8601_utc()

    user = {
        # id is always generated server-side; any client-supplied id is
        # rejected earlier by routes.py.
        "id": str(uuid.uuid4()),
        "first_name": data["first_name"],
        "last_name": data["last_name"],
        "email": normalized_email,
        # company is optional and defaults to null when absent.
        "company": data.get("company"),
        # role defaults to "attendee" when not provided on creation.
        "role": data.get("role", "attendee"),
        "created_at": timestamp,
        "updated_at": timestamp,
    }

    return repo.create(user)


def get_user(repo, user_id: str) -> dict:
    """
    Retrieve a single user by its UUID.

    Parameters
    ----------
    repo : AbstractUserRepository
        The persistence backend, injected by the caller.
    user_id : str
        The UUID of the user to retrieve.

    Returns
    -------
    dict
        The complete stored user dict.

    Raises
    ------
    UserNotFound
        If no user with the given UUID exists (Requirements: REQ-USR-E03.2).
    """
    user = repo.get_by_id(user_id)
    if user is None:
        raise UserNotFound(user_id)
    return user


def list_users(
    repo,
    role: str | None,
    email: str | None,
    page: int,
    page_size: int,
) -> dict:
    """
    Return a paginated, optionally filtered ``UserPage`` dict.

    The ``email`` filter is normalized to lowercase before being passed to the
    repository so the comparison is case-insensitive (Requirements:
    REQ-USR-B03.2). The ``role`` filter is applied verbatim. Both filters combine
    with logical AND in the repository (Requirements: REQ-USR-B03.3).

    Parameters
    ----------
    repo : AbstractUserRepository
        The persistence backend, injected by the caller.
    role : str | None
        Optional exact-match role filter.
    email : str | None
        Optional case-insensitive email filter.
    page : int
        1-based page index.
    page_size : int
        Number of items per page.

    Returns
    -------
    dict
        A ``UserPage`` dict of the shape
        ``{"items": [...], "page": page, "page_size": page_size, "total": total}``
        conforming to the ``UserPage`` contract schema (Requirements:
        REQ-USR-E02.3). ``total`` is the count of all users matching the filters
        across every page; a page beyond the last one yields an empty ``items``
        list with ``total`` still correct (Requirements: REQ-USR-E02.6).
    """
    # Normalize the email filter to lowercase before delegating; the repository
    # also normalizes defensively, but we honor the domain contract here.
    normalized_email = email.lower() if email is not None else None

    items, total = repo.list_users(role, normalized_email, page, page_size)

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
    }


def replace_user(repo, user_id: str, data: dict) -> dict:
    """
    Fully replace the modifiable fields of an existing user (PUT semantics).

    The input ``data`` is assumed to have already passed the structural
    validation performed by ``routes.py``. This function applies the domain
    rules:

    - loads the existing user, raising :class:`UserNotFound` if it does not
      exist (Requirements: REQ-USR-E04.3);
    - replaces the whole set of modifiable fields (``first_name``,
      ``last_name``, ``email``, ``company``, ``role``); ``company`` defaults to
      ``None`` and ``role`` defaults to ``"attendee"`` when absent from the body
      (Requirements: REQ-USR-E04.1);
    - normalizes ``email`` to lowercase (Requirements: REQ-USR-B02.2);
    - enforces global case-insensitive email uniqueness, but treats a
      self-update (same email already owned by this user) as *not* a conflict
      (Requirements: REQ-USR-B01.2, REQ-USR-B01.3);
    - refreshes ``updated_at`` to the current ISO 8601 UTC timestamp while
      leaving ``created_at`` untouched (Requirements: REQ-USR-E04.2).

    Parameters
    ----------
    repo : AbstractUserRepository
        The persistence backend, injected by the caller.
    user_id : str
        The UUID of the user to replace.
    data : dict
        Validated replacement payload.

    Returns
    -------
    dict
        The complete updated user dict as returned by the repository.

    Raises
    ------
    UserNotFound
        If no user with the given UUID exists.
    EmailAlreadyExists
        If the normalized new email belongs to a different user.
    """
    existing = repo.get_by_id(user_id)
    if existing is None:
        raise UserNotFound(user_id)

    # Normalize the incoming email before any comparison or persistence.
    normalized_email = data["email"].lower()

    # Email uniqueness: a match on another user is a conflict; the user being
    # updated owning that email (self-update) is explicitly allowed.
    conflict = repo.get_by_email(normalized_email)
    if conflict is not None and conflict["id"] != user_id:
        raise EmailAlreadyExists(normalized_email)

    # Full replace of the modifiable fields. Omitted optional fields fall back
    # to their defaults: company -> None, role -> "attendee".
    fields = {
        "first_name": data["first_name"],
        "last_name": data["last_name"],
        "email": normalized_email,
        "company": data.get("company"),
        "role": data.get("role", "attendee"),
        # created_at is left untouched; only updated_at moves forward.
        "updated_at": _now_iso8601_utc(),
    }

    return repo.update(user_id, fields)


def update_user(repo, user_id: str, data: dict) -> dict:
    """
    Partially update an existing user (PATCH semantics).

    Only the fields present in ``data`` are changed. The input is assumed to
    have already passed the structural validation performed by ``routes.py``.
    This function applies the domain rules:

    - loads the existing user, raising :class:`UserNotFound` if it does not
      exist (Requirements: REQ-USR-E05.5);
    - if the body is empty (``{}``), returns the current user unchanged and does
      *not* touch ``updated_at`` (Requirements: REQ-USR-E05.2);
    - when ``email`` is among the provided fields, normalizes it to lowercase
      (Requirements: REQ-USR-B02.2) and enforces global case-insensitive email
      uniqueness, treating a self-update as not a conflict (Requirements:
      REQ-USR-B01.2, REQ-USR-B01.3);
    - refreshes ``updated_at`` to the current ISO 8601 UTC timestamp only when
      at least one field is actually modified, leaving ``created_at`` untouched
      (Requirements: REQ-USR-E05.3).

    Parameters
    ----------
    repo : AbstractUserRepository
        The persistence backend, injected by the caller.
    user_id : str
        The UUID of the user to update.
    data : dict
        Validated partial-update payload; may be empty.

    Returns
    -------
    dict
        The complete (possibly unchanged) user dict.

    Raises
    ------
    UserNotFound
        If no user with the given UUID exists.
    EmailAlreadyExists
        If the normalized new email belongs to a different user.
    """
    existing = repo.get_by_id(user_id)
    if existing is None:
        raise UserNotFound(user_id)

    # Empty body: nothing to modify. Return the current user untouched, leaving
    # updated_at exactly as it was.
    if not data:
        return existing

    # Build the set of fields to apply, taking only what the client provided.
    fields: dict = {}
    for key in ("first_name", "last_name", "email", "company", "role"):
        if key in data:
            fields[key] = data[key]

    # Normalize the email and enforce uniqueness only when email is being changed.
    if "email" in fields:
        normalized_email = fields["email"].lower()
        fields["email"] = normalized_email
        conflict = repo.get_by_email(normalized_email)
        if conflict is not None and conflict["id"] != user_id:
            raise EmailAlreadyExists(normalized_email)

    # At least one field was provided: bump updated_at; created_at is untouched.
    fields["updated_at"] = _now_iso8601_utc()

    return repo.update(user_id, fields)


def delete_user(repo, user_id: str) -> None:
    """
    Delete a user by its UUID.

    Parameters
    ----------
    repo : AbstractUserRepository
        The persistence backend, injected by the caller.
    user_id : str
        The UUID of the user to delete.

    Returns
    -------
    None

    Raises
    ------
    UserNotFound
        If no user with the given UUID exists, including the case where it was
        already deleted (Requirements: REQ-USR-E06.2, REQ-USR-E06.3).
    """
    if not repo.delete(user_id):
        raise UserNotFound(user_id)
