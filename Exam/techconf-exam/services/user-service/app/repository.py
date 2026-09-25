"""
repository.py — Persistence layer for user-service.

Defines the :class:`AbstractUserRepository` interface and its concrete
implementations. The business layer depends only on the abstract interface,
which guarantees the storage backend can be swapped without touching domain
logic (Requirements: REQ-USR-P03.5).

This module must NOT import Flask: it is a pure persistence layer.

The repository always stores and returns the email already normalized to
lowercase; normalization is performed by the business layer before calling
the repository. The methods here are defensive and normalize the email filter
again to guard against callers that forget to do so.

Requirements: REQ-USR-P03
"""

from abc import ABC, abstractmethod


class AbstractUserRepository(ABC):
    """
    Abstract persistence interface for users.

    A user is represented as a plain ``dict`` with the following keys::

        id, first_name, last_name, email, company, role, created_at, updated_at

    Concrete implementations (memory, json, sqlite) provide the storage
    mechanics; the business layer only ever sees this interface, keeping the
    backends interchangeable (Requirements: REQ-USR-P03.5).
    """

    @abstractmethod
    def create(self, user_data: dict) -> dict:
        """
        Persist a new user.

        Parameters
        ----------
        user_data : dict
            Complete user dict including ``id``, ``email`` (already normalized),
            ``role``, ``created_at`` and ``updated_at``.

        Returns
        -------
        dict
            The stored user dict.
        """
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, user_id: str) -> dict | None:
        """Retrieve a user by UUID string. Return ``None`` if not found."""
        raise NotImplementedError

    @abstractmethod
    def get_by_email(self, email: str) -> dict | None:
        """
        Retrieve a user by (already normalized) email.

        Return ``None`` if no user has that email.
        """
        raise NotImplementedError

    @abstractmethod
    def list_users(
        self,
        role: str | None,
        email: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int]:
        """
        Return the tuple ``(items, total)``.

        Parameters
        ----------
        role : str | None
            If provided, only users whose ``role`` matches exactly are kept.
        email : str | None
            If provided, only users whose ``email`` matches (case-insensitive)
            are kept.
        page : int
            1-based page index.
        page_size : int
            Number of items per page.

        Returns
        -------
        tuple[list[dict], int]
            ``items`` is the slice of users for the requested page after
            applying the filters; ``total`` is the count of all users matching
            the filters across every page.
        """
        raise NotImplementedError

    @abstractmethod
    def update(self, user_id: str, fields: dict) -> dict | None:
        """
        Apply ``fields`` onto the existing user and return the updated dict.

        Handles both PUT (full replace) and PATCH (partial update): the caller
        (business layer) decides which fields to pass. Return ``None`` if the
        user does not exist.
        """
        raise NotImplementedError

    @abstractmethod
    def delete(self, user_id: str) -> bool:
        """Delete a user. Return ``True`` if deleted, ``False`` if not found."""
        raise NotImplementedError


class MemoryUserRepository(AbstractUserRepository):
    """
    In-memory user repository backed by a Python ``dict``.

    Data lives in ``{uuid_str: user_dict}`` and is lost when the process
    restarts (Requirements: REQ-USR-P03.1). List and filter operations are
    O(n), which is acceptable for the exam context. A fresh instance is used
    per unit test.
    """

    def __init__(self) -> None:
        # Internal store: maps the user's UUID (as a string) to its dict.
        self._users: dict[str, dict] = {}

    def create(self, user_data: dict) -> dict:
        # Store a defensive copy so external mutations of the caller's dict do
        # not leak into the repository state.
        stored = dict(user_data)
        self._users[stored["id"]] = stored
        # Return a copy so callers cannot mutate the stored record directly.
        return dict(stored)

    def get_by_id(self, user_id: str) -> dict | None:
        user = self._users.get(user_id)
        return dict(user) if user is not None else None

    def get_by_email(self, email: str) -> dict | None:
        # Defensive normalization: business layer already lowercases the email,
        # but guard against callers that do not.
        normalized = email.lower()
        for user in self._users.values():
            if user.get("email", "").lower() == normalized:
                return dict(user)
        return None

    def list_users(
        self,
        role: str | None,
        email: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int]:
        # Defensive normalization of the email filter.
        email_filter = email.lower() if email is not None else None

        # Apply filters (role and email combine with logical AND). O(n) scan.
        matched: list[dict] = []
        for user in self._users.values():
            if role is not None and user.get("role") != role:
                continue
            if email_filter is not None and user.get("email", "").lower() != email_filter:
                continue
            matched.append(dict(user))

        total = len(matched)

        # 1-based pagination. If the page is beyond the last page, the slice is
        # empty but total remains correct.
        start = (page - 1) * page_size
        end = start + page_size
        items = matched[start:end]

        return items, total

    def update(self, user_id: str, fields: dict) -> dict | None:
        user = self._users.get(user_id)
        if user is None:
            return None
        # Apply the provided fields onto the existing record. The business layer
        # decides which fields to include for PUT (full) vs PATCH (partial).
        user.update(fields)
        return dict(user)

    def delete(self, user_id: str) -> bool:
        if user_id in self._users:
            del self._users[user_id]
            return True
        return False
