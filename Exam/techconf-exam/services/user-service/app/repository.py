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

import json
import os
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path


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


class JsonUserRepository(AbstractUserRepository):
    """
    File-backed user repository serializing to a JSON array on disk.

    Data is persisted in ``{DATA_DIR}/users.json`` as a JSON array of user
    dicts (Requirements: REQ-USR-P03.2). ``DATA_DIR`` is created automatically
    if it does not exist, and the data file is initialized with an empty array
    ``[]`` on first use.

    Every write operation re-reads the file, applies the change in memory and
    rewrites the whole file. Writes are **atomic**: the payload is first written
    to a temporary file (``users.json.tmp``) in the same directory and then
    moved onto the final file with :func:`os.replace`, which avoids leaving a
    partially written ``users.json`` behind if the process crashes mid-write.

    List and filter operations are O(n), matching the semantics of
    :class:`MemoryUserRepository`, keeping the backends interchangeable
    (Requirements: REQ-USR-P03.5).
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)
        # Create DATA_DIR automatically if it does not exist.
        os.makedirs(self._data_dir, exist_ok=True)
        self._file = self._data_dir / "users.json"
        self._tmp_file = self._data_dir / "users.json.tmp"
        # Ensure the data file exists with an empty array on first use, loading
        # any pre-existing state at startup.
        if not self._file.exists():
            self._write_all([])

    def _read_all(self) -> list[dict]:
        """Load the full list of users from disk."""
        with self._file.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _write_all(self, users: list[dict]) -> None:
        """
        Persist the full list of users atomically.

        Write to a temporary file in the same directory, then atomically
        replace the definitive file (Requirements: REQ-USR-P03.2).
        """
        with self._tmp_file.open("w", encoding="utf-8") as fh:
            json.dump(users, fh, ensure_ascii=False, indent=2)
        os.replace(self._tmp_file, self._file)

    def create(self, user_data: dict) -> dict:
        users = self._read_all()
        stored = dict(user_data)
        users.append(stored)
        self._write_all(users)
        return dict(stored)

    def get_by_id(self, user_id: str) -> dict | None:
        for user in self._read_all():
            if user.get("id") == user_id:
                return dict(user)
        return None

    def get_by_email(self, email: str) -> dict | None:
        # Defensive normalization: business layer already lowercases the email,
        # but guard against callers that do not.
        normalized = email.lower()
        for user in self._read_all():
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
        for user in self._read_all():
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
        users = self._read_all()
        for index, user in enumerate(users):
            if user.get("id") == user_id:
                # Apply the provided fields onto the existing record. The
                # business layer decides which fields to include for PUT (full)
                # vs PATCH (partial).
                user.update(fields)
                users[index] = user
                self._write_all(users)
                return dict(user)
        return None

    def delete(self, user_id: str) -> bool:
        users = self._read_all()
        remaining = [user for user in users if user.get("id") != user_id]
        if len(remaining) == len(users):
            return False
        self._write_all(remaining)
        return True

class SqliteUserRepository(AbstractUserRepository):
    """
    SQLite-backed user repository using only the standard-library ``sqlite3``.

    Data is persisted to ``{data_dir}/users.db`` (Requirements: REQ-USR-P03.3,
    REQ-USR-P03.6). ``DATA_DIR`` is created automatically if it does not exist.
    The ``users`` table is created on construction with
    ``CREATE TABLE IF NOT EXISTS``.

    The stored ``email`` is always already normalized to lowercase by the
    business layer; the ``UNIQUE`` constraint on ``email`` enforces global
    uniqueness at the storage level. As with the other backends, the email
    filter in :meth:`list_users` is normalized defensively.

    All queries are parameterized (``?`` placeholders) — no value is ever
    interpolated into SQL text — to prevent SQL injection.
    """

    # Column order shared by every SELECT so rows map cleanly onto user dicts.
    _COLUMNS = (
        "id",
        "first_name",
        "last_name",
        "email",
        "company",
        "role",
        "created_at",
        "updated_at",
    )

    def __init__(self, data_dir) -> None:
        # ``data_dir`` may be a ``Path`` or a ``str``; ``os`` handles both.
        self._data_dir = data_dir
        os.makedirs(self._data_dir, exist_ok=True)
        self._db_path = os.path.join(str(data_dir), "users.db")
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        # ``sqlite3.Row`` lets us read columns by name and build dicts easily.
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id          TEXT PRIMARY KEY,
                    first_name  TEXT NOT NULL,
                    last_name   TEXT NOT NULL,
                    email       TEXT NOT NULL UNIQUE,
                    company     TEXT,
                    role        TEXT NOT NULL DEFAULT 'attendee',
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        # Materialize a plain dict so callers never hold a live cursor row.
        return {key: row[key] for key in SqliteUserRepository._COLUMNS}

    def create(self, user_data: dict) -> dict:
        stored = dict(user_data)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users
                    (id, first_name, last_name, email, company, role,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stored["id"],
                    stored["first_name"],
                    stored["last_name"],
                    stored["email"],
                    stored.get("company"),
                    stored.get("role", "attendee"),
                    stored["created_at"],
                    stored["updated_at"],
                ),
            )
        # Return the canonical stored representation.
        return self.get_by_id(stored["id"])

    def get_by_id(self, user_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return self._row_to_dict(row) if row is not None else None

    def get_by_email(self, email: str) -> dict | None:
        # Defensive normalization: business layer already lowercases the email.
        normalized = email.lower()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email = ?",
                (normalized,),
            ).fetchone()
        return self._row_to_dict(row) if row is not None else None

    def list_users(
        self,
        role: str | None,
        email: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict], int]:
        # Defensive normalization of the email filter.
        email_filter = email.lower() if email is not None else None

        # Build a parameterized WHERE clause: filters combine with logical AND.
        # Values live only in the params tuple — never interpolated into SQL.
        conditions: list[str] = []
        params: list[str] = []
        if role is not None:
            conditions.append("role = ?")
            params.append(role)
        if email_filter is not None:
            conditions.append("email = ?")
            params.append(email_filter)

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""

        with self._connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM users{where_clause}",
                params,
            ).fetchone()[0]

            # 1-based pagination via LIMIT/OFFSET. A page beyond the last one
            # yields an empty slice while ``total`` stays correct.
            offset = (page - 1) * page_size
            rows = conn.execute(
                f"SELECT * FROM users{where_clause} "
                "ORDER BY created_at, id LIMIT ? OFFSET ?",
                params + [page_size, offset],
            ).fetchall()

        items = [self._row_to_dict(row) for row in rows]
        return items, total

    def update(self, user_id: str, fields: dict) -> dict | None:
        # Only touch a user that actually exists.
        if self.get_by_id(user_id) is None:
            return None

        # Restrict updatable columns to the known schema and build a
        # parameterized SET clause. ``id`` is never updated.
        updatable = [col for col in self._COLUMNS if col != "id"]
        assignments: list[str] = []
        params: list = []
        for col in updatable:
            if col in fields:
                assignments.append(f"{col} = ?")
                params.append(fields[col])

        if assignments:
            params.append(user_id)
            with self._connect() as conn:
                conn.execute(
                    f"UPDATE users SET {', '.join(assignments)} WHERE id = ?",
                    params,
                )

        return self.get_by_id(user_id)

    def delete(self, user_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM users WHERE id = ?",
                (user_id,),
            )
            return cursor.rowcount > 0
