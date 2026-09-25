"""
routes.py — HTTP layer (Flask) for user-service.

This module owns the HTTP concerns of the service:

  1. Routing (Flask ``Blueprint`` named ``api_blueprint``).
  2. Body parsing — a non-parsable JSON body yields ``400 MALFORMED_JSON``.
  3. Formal input validation (types, lengths, formats, required fields and
     ``additionalProperties: false``) — any violation yields
     ``422 VALIDATION_ERROR`` with a ``details`` map of the offending fields.
  4. Delegation to :mod:`app.business` for all domain rules (email
     normalization, uniqueness, UUID generation, timestamps).
  5. Translation of domain exceptions into HTTP responses.
  6. Serialization of responses conforming to the OpenAPI ``User`` /
     ``Error`` schemas.

The module deliberately contains **no domain logic**: it validates the shape
of the request and hands validated data to ``business.py``. The repository is
retrieved from ``current_app.config["REPO"]`` on each request.

Requirements: REQ-USR-E01, REQ-USR-F01, REQ-USR-F02, REQ-USR-B01, REQ-USR-P01
"""

import re
import uuid

from flask import Blueprint, current_app, jsonify, make_response, request
from werkzeug.exceptions import BadRequest, MethodNotAllowed

from app import business

# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------
# main.py imports this symbol and registers it on the application:
#     from app.routes import api_blueprint
#     app.register_blueprint(api_blueprint)
api_blueprint = Blueprint("api", __name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Allowed roles (OpenAPI ``Role`` enum).
_VALID_ROLES = ("attendee", "speaker", "organizer")

# Fields accepted by the UserCreate / UserUpdate schemas. Anything else is an
# unknown field and must be rejected (additionalProperties: false). Notably the
# ``id`` field is NOT part of this set, so a client-supplied ``id`` is rejected.
_ALLOWED_USER_FIELDS = ("first_name", "last_name", "email", "company", "role")

# Output field order for the ``User`` response schema.
_USER_OUTPUT_FIELDS = (
    "id",
    "first_name",
    "last_name",
    "email",
    "company",
    "role",
    "created_at",
    "updated_at",
)

# Pragmatic email format check. The OpenAPI ``format: email`` is intentionally
# loose; this regex accepts a single ``@`` with non-empty, non-whitespace local
# and domain parts and at least one dot in the domain.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------------------
# Validation error
# ---------------------------------------------------------------------------
class ValidationError(Exception):
    """
    Raised by the validation helpers to signal a ``422 VALIDATION_ERROR``.

    Carries a ``details`` dict mapping each offending field name to a short
    human-readable reason, surfaced in the error response ``details`` object
    (Requirements: REQ-USR-F02.8, REQ-USR-P01.1).
    """

    def __init__(self, details: dict, message: str = "Validation failed") -> None:
        super().__init__(message)
        self.message = message
        self.details = details


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------
def _error(code: str, message: str, status: int, details: dict | None = None):
    """
    Build a standard error response tuple conforming to the ``Error`` schema.

    Returns ``(response, status)`` where ``response`` is a Flask JSON response
    of the shape ``{"error": {"code", "message", "details"?}}``. ``details`` is
    omitted entirely when ``None`` (Requirements: REQ-USR-P01.1).
    """
    body: dict = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return jsonify(body), status


def _serialize_user(user: dict) -> dict:
    """
    Project a stored user dict onto the OpenAPI ``User`` response schema.

    Returns only the fields defined by the ``User`` schema, in a stable order
    (Requirements: REQ-USR-F01.1, REQ-USR-F01.7).
    """
    return {field: user.get(field) for field in _USER_OUTPUT_FIELDS}


def _repo():
    """Return the repository injected onto the app config by main.py."""
    return current_app.config["REPO"]


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------
def _is_valid_uuid_v4(value) -> bool:
    """
    Return ``True`` if ``value`` is a syntactically valid UUID **version 4**.

    Used by the ``{id}`` path-parameter validation in later route tasks
    (GET/PUT/PATCH/DELETE by id). A value is accepted only if it parses as a
    UUID, is version 4, and round-trips to the same canonical string (this
    rejects malformed or non-canonical inputs).
    """
    if not isinstance(value, str):
        return False
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return parsed.version == 4 and str(parsed) == value.lower()


def _validate_user_body(data, partial: bool) -> dict:
    """
    Validate a UserCreate (``partial=False``) or UserUpdate (``partial=True``)
    body and return the validated dict.

    Rules enforced (Requirements: REQ-USR-F01.4/6, REQ-USR-F02.1–8):

    - the body must be a JSON object;
    - ``additionalProperties: false`` — any field outside the allowed set
      (including ``id``) is rejected;
    - for ``partial=False``, ``first_name``, ``last_name`` and ``email`` are
      required; for ``partial=True`` every field is optional;
    - ``first_name`` / ``last_name``: non-empty string of length 1..50;
    - ``email``: string matching a valid email format;
    - ``company``: ``null`` or a string of length 1..100;
    - ``role``: one of ``attendee`` / ``speaker`` / ``organizer``.

    On any violation a :class:`ValidationError` is raised carrying a per-field
    ``details`` map; the caller translates it into ``422 VALIDATION_ERROR``.
    """
    details: dict = {}

    # The body must be a JSON object (not a list, string, number, etc.).
    if not isinstance(data, dict):
        raise ValidationError(
            {"body": "must be a JSON object"},
            "Request body must be a JSON object",
        )

    # additionalProperties: false — reject any unknown field. This also covers
    # a client-supplied ``id`` (never accepted in input, REQ-USR-F01.4).
    for key in data:
        if key not in _ALLOWED_USER_FIELDS:
            details[key] = "unknown field is not allowed"

    # Required fields (only for full-body / create validation).
    if not partial:
        for field in ("first_name", "last_name", "email"):
            if field not in data:
                details[field] = "required field is missing"

    # first_name / last_name: non-empty string, length 1..50.
    for field in ("first_name", "last_name"):
        if field in data:
            value = data[field]
            if not isinstance(value, str):
                details[field] = "must be a string"
            elif not (1 <= len(value) <= 50):
                details[field] = "length must be between 1 and 50 characters"

    # email: string in a valid email format.
    if "email" in data:
        value = data["email"]
        if not isinstance(value, str):
            details["email"] = "must be a string"
        elif not _EMAIL_RE.match(value):
            details["email"] = "must be a valid email address"

    # company: null OR string of length 1..100.
    if "company" in data:
        value = data["company"]
        if value is not None:
            if not isinstance(value, str):
                details["company"] = "must be a string or null"
            elif not (1 <= len(value) <= 100):
                details["company"] = "length must be between 1 and 100 characters"

    # role: enum attendee|speaker|organizer.
    if "role" in data:
        value = data["role"]
        if value not in _VALID_ROLES:
            details["role"] = f"must be one of {', '.join(_VALID_ROLES)}"

    if details:
        raise ValidationError(details)

    return data


def _parse_json_body():
    """
    Parse the request body as JSON, raising :class:`werkzeug.BadRequest` when
    the body is missing or not parsable.

    Using ``get_json(silent=False)`` lets Flask/Werkzeug raise a ``BadRequest``
    for a malformed body, which the blueprint's ``BadRequest`` handler turns
    into the standard ``400 MALFORMED_JSON`` response (Requirements:
    REQ-USR-E01.4, REQ-USR-P01.3).
    """
    # force=True: parse regardless of the Content-Type header.
    # silent=False: raise BadRequest on a non-parsable body.
    return request.get_json(force=True, silent=False)


# ---------------------------------------------------------------------------
# Error handlers (blueprint-scoped)
# ---------------------------------------------------------------------------
@api_blueprint.app_errorhandler(BadRequest)
def _handle_bad_request(_exc):
    """
    Translate a malformed JSON body into the standard ``400 MALFORMED_JSON``.

    Werkzeug raises :class:`BadRequest` when JSON parsing fails; we normalize it
    to the platform error format (Requirements: REQ-USR-E01.4, REQ-USR-P01.3).
    """
    return _error("MALFORMED_JSON", "Request body is not valid JSON", 400)


@api_blueprint.app_errorhandler(MethodNotAllowed)
def _handle_method_not_allowed(exc):
    """
    Translate an unsupported HTTP method into ``405 METHOD_NOT_ALLOWED``.

    Werkzeug raises :class:`MethodNotAllowed` when a known route path is hit
    with a method it does not support (e.g. ``DELETE`` on the ``/api/v1/users``
    collection, or ``POST`` on ``/api/v1/users/<id>``). We normalize it to the
    platform error format and set the ``Allow`` header listing the methods the
    matched endpoint accepts (Requirements: REQ-USR-E08.1–2, REQ-USR-P01.1).

    The set of valid methods is carried on the exception as
    ``exc.valid_methods``; when Werkzeug does not populate it we fall back to
    the ``Allow`` header Werkzeug placed on its own response.
    """
    resp, status = _error(
        "METHOD_NOT_ALLOWED",
        "The HTTP method is not allowed for this endpoint",
        405,
    )
    response = make_response(resp, status)

    # Prefer the valid methods carried on the exception; otherwise reuse the
    # Allow header Werkzeug already computed for the matched rule.
    allowed = getattr(exc, "valid_methods", None)
    if allowed is None:
        existing = getattr(exc, "get_headers", None)
        # exc.get_headers() yields (name, value) pairs including "Allow".
        if existing is not None:
            for name, value in exc.get_headers():
                if name.lower() == "allow":
                    allowed = [m.strip() for m in value.split(",") if m.strip()]
                    break

    if allowed:
        response.headers["Allow"] = ", ".join(allowed)

    return response


# ---------------------------------------------------------------------------
# POST /api/v1/users — Create a user (Task 10.1)
# ---------------------------------------------------------------------------
@api_blueprint.route("/api/v1/users", methods=["POST"])
def create_user():
    """
    Create a new user.

    Flow (Requirements: REQ-USR-E01.1–8, REQ-USR-F01, REQ-USR-F02, REQ-USR-B01):

    1. Parse the JSON body — non-parsable body -> ``400 MALFORMED_JSON``
       (handled by :func:`_handle_bad_request`).
    2. Validate the body against ``UserCreate`` -> ``422 VALIDATION_ERROR`` on
       any violation, including a client-supplied ``id`` or unknown fields.
    3. Delegate to :func:`app.business.create_user` — a duplicate email
       (case-insensitive) surfaces as ``EmailAlreadyExists`` ->
       ``409 EMAIL_ALREADY_EXISTS``.
    4. On success respond ``201`` with the ``User`` body and a ``Location``
       header pointing at the created resource.
    """
    # 1. Parse — may raise BadRequest -> handled as 400 MALFORMED_JSON.
    body = _parse_json_body()

    # 2. Validate the create payload (full body, not partial).
    try:
        validated = _validate_user_body(body, partial=False)
    except ValidationError as exc:
        return _error("VALIDATION_ERROR", exc.message, 422, exc.details)

    # 3. Delegate to the domain layer.
    try:
        created = business.create_user(_repo(), validated)
    except business.EmailAlreadyExists:
        return _error(
            "EMAIL_ALREADY_EXISTS",
            "A user with this email already exists",
            409,
        )

    # 4. Success: 201 + Location header + serialized User body.
    response = jsonify(_serialize_user(created))
    response.status_code = 201
    response.headers["Location"] = f"/api/v1/users/{created['id']}"
    return response


# ---------------------------------------------------------------------------
# GET /api/v1/users — List users (paginated, filterable) (Task 11.1)
# ---------------------------------------------------------------------------
@api_blueprint.route("/api/v1/users", methods=["GET"])
def list_users():
    """
    Return a paginated, optionally filtered list of users.

    Flow (Requirements: REQ-USR-E02.1–6, REQ-USR-B03.5–6):

    1. Read query params: ``page`` (default 1), ``page_size`` (default 20),
       ``role`` (optional), ``email`` (optional).
    2. Validate them -> ``422 VALIDATION_ERROR`` on any violation:
       - ``page`` must be an integer >= 1;
       - ``page_size`` must be an integer in [1, 100];
       - ``role``, if present, must be one of attendee/speaker/organizer
         (an empty string is rejected);
       - ``email``, if present, must be a non-empty string.
    3. Delegate to :func:`app.business.list_users`, which applies the filters
       and pagination and returns a ``UserPage`` dict.
    4. Serialize each raw user in ``items`` via :func:`_serialize_user` and
       respond ``200`` with the ``UserPage`` body. A page beyond the last one
       yields an empty ``items`` list with a correct ``total``.
    """
    details: dict = {}

    # page: integer >= 1 (default 1). request.args.get returns the raw string.
    page_raw = request.args.get("page", "1")
    page = 1
    try:
        page = int(page_raw)
        if page < 1:
            details["page"] = "must be an integer greater than or equal to 1"
    except (TypeError, ValueError):
        details["page"] = "must be an integer greater than or equal to 1"

    # page_size: integer in [1, 100] (default 20).
    page_size_raw = request.args.get("page_size", "20")
    page_size = 20
    try:
        page_size = int(page_size_raw)
        if not (1 <= page_size <= 100):
            details["page_size"] = "must be an integer between 1 and 100"
    except (TypeError, ValueError):
        details["page_size"] = "must be an integer between 1 and 100"

    # role: optional; if present must be a valid enum value (empty string
    # is present-but-invalid and therefore rejected).
    role = None
    if "role" in request.args:
        role = request.args.get("role")
        if role not in _VALID_ROLES:
            details["role"] = f"must be one of {', '.join(_VALID_ROLES)}"

    # email: optional; if present must be a non-empty string.
    email = None
    if "email" in request.args:
        email = request.args.get("email")
        if not isinstance(email, str) or email == "":
            details["email"] = "must be a non-empty string"

    if details:
        return _error("VALIDATION_ERROR", "Validation failed", 422, details)

    # Delegate to the domain layer for filtering + pagination.
    result = business.list_users(_repo(), role, email, page, page_size)

    # Serialize each raw user dict onto the ``User`` response schema.
    body = {
        "items": [_serialize_user(item) for item in result["items"]],
        "page": result["page"],
        "page_size": result["page_size"],
        "total": result["total"],
    }
    return jsonify(body), 200


# ---------------------------------------------------------------------------
# GET /api/v1/users/{id} — Retrieve a user by id (Task 12.1)
# ---------------------------------------------------------------------------
@api_blueprint.route("/api/v1/users/<id>", methods=["GET"])
def get_user(id):
    """
    Retrieve a single user by its UUID.

    Flow (Requirements: REQ-USR-E03.1–3, REQ-USR-P01):

    1. Validate the ``{id}`` path parameter as a UUID v4 via
       :func:`_is_valid_uuid_v4` — a malformed id -> ``422 VALIDATION_ERROR``.
    2. Delegate to :func:`app.business.get_user`; a syntactically valid but
       unknown id surfaces as ``UserNotFound`` -> ``404 NOT_FOUND``.
    3. On success respond ``200`` with the serialized ``User`` body; the
       ``id`` in the response equals the UUID from the path.

    This handler establishes the ``/api/v1/users/<id>`` route path; later
    tasks register PUT/PATCH/DELETE on the same path as separate functions,
    reusing :func:`_is_valid_uuid_v4` for path-parameter validation.
    """
    # 1. Validate the path parameter as a UUID v4.
    if not _is_valid_uuid_v4(id):
        return _error(
            "VALIDATION_ERROR",
            "Validation failed",
            422,
            {"id": "must be a valid UUID v4"},
        )

    # 2. Delegate to the domain layer.
    try:
        user = business.get_user(_repo(), id)
    except business.UserNotFound:
        return _error("NOT_FOUND", "User not found", 404)

    # 3. Success: 200 + serialized User body.
    return jsonify(_serialize_user(user)), 200


# ---------------------------------------------------------------------------
# PUT /api/v1/users/{id} — Full replace of a user (Task 13.1)
# ---------------------------------------------------------------------------
@api_blueprint.route("/api/v1/users/<id>", methods=["PUT"])
def replace_user(id):
    """
    Fully replace an existing user (PUT semantics).

    Flow (Requirements: REQ-USR-E04.1–6, REQ-USR-P01):

    1. Validate the ``{id}`` path parameter as a UUID v4 via
       :func:`_is_valid_uuid_v4` — a malformed id -> ``422 VALIDATION_ERROR``.
    2. Parse the JSON body — non-parsable body -> ``400 MALFORMED_JSON``
       (handled by :func:`_handle_bad_request`).
    3. Validate the body against ``UserCreate`` (full body, same rules as POST:
       ``first_name``/``last_name``/``email`` required, ``additionalProperties:
       false``, a client-supplied ``id`` rejected) -> ``422 VALIDATION_ERROR``.
    4. Delegate to :func:`app.business.replace_user`; an unknown id surfaces as
       ``UserNotFound`` -> ``404 NOT_FOUND``, and an email owned by a *different*
       user surfaces as ``EmailAlreadyExists`` -> ``409 EMAIL_ALREADY_EXISTS``
       (a self-update reusing the user's own email is not a conflict).
    5. On success respond ``200`` with the serialized ``User`` body. The domain
       layer defaults ``company`` to ``null`` and ``role`` to ``attendee`` when
       omitted, refreshes ``updated_at`` and leaves ``created_at`` untouched.
    """
    # 1. Validate the path parameter as a UUID v4.
    if not _is_valid_uuid_v4(id):
        return _error(
            "VALIDATION_ERROR",
            "Validation failed",
            422,
            {"id": "must be a valid UUID v4"},
        )

    # 2. Parse — may raise BadRequest -> handled as 400 MALFORMED_JSON.
    body = _parse_json_body()

    # 3. Validate the replacement payload (full body, not partial).
    try:
        validated = _validate_user_body(body, partial=False)
    except ValidationError as exc:
        return _error("VALIDATION_ERROR", exc.message, 422, exc.details)

    # 4. Delegate to the domain layer.
    try:
        updated = business.replace_user(_repo(), id, validated)
    except business.UserNotFound:
        return _error("NOT_FOUND", "User not found", 404)
    except business.EmailAlreadyExists:
        return _error(
            "EMAIL_ALREADY_EXISTS",
            "A user with this email already exists",
            409,
        )

    # 5. Success: 200 + serialized User body.
    return jsonify(_serialize_user(updated)), 200


# ---------------------------------------------------------------------------
# PATCH /api/v1/users/{id} — Partial update of a user (Task 14.1)
# ---------------------------------------------------------------------------
@api_blueprint.route("/api/v1/users/<id>", methods=["PATCH"])
def update_user(id):
    """
    Partially update an existing user (PATCH semantics).

    Flow (Requirements: REQ-USR-E05.1–8, REQ-USR-P01):

    1. Validate the ``{id}`` path parameter as a UUID v4 via
       :func:`_is_valid_uuid_v4` — a malformed id -> ``422 VALIDATION_ERROR``.
    2. Parse the JSON body — non-parsable body -> ``400 MALFORMED_JSON``
       (handled by :func:`_handle_bad_request`).
    3. Validate the body against ``UserUpdate`` (partial body: every field is
       optional, ``additionalProperties: false`` still rejects unknown fields
       including a client-supplied ``id``, and field constraints still apply
       when a field is present) -> ``422 VALIDATION_ERROR``. An empty object
       ``{}`` is valid.
    4. Delegate to :func:`app.business.update_user`; an unknown id surfaces as
       ``UserNotFound`` -> ``404 NOT_FOUND``, and an email owned by a *different*
       user surfaces as ``EmailAlreadyExists`` -> ``409 EMAIL_ALREADY_EXISTS``
       (a self-update reusing the user's own email is not a conflict).
    5. On success respond ``200`` with the serialized ``User`` body. Only the
       provided fields are changed; the domain layer refreshes ``updated_at``
       when at least one field is modified and leaves it (and ``created_at``)
       untouched for an empty body.
    """
    # 1. Validate the path parameter as a UUID v4.
    if not _is_valid_uuid_v4(id):
        return _error(
            "VALIDATION_ERROR",
            "Validation failed",
            422,
            {"id": "must be a valid UUID v4"},
        )

    # 2. Parse — may raise BadRequest -> handled as 400 MALFORMED_JSON.
    body = _parse_json_body()

    # 3. Validate the partial-update payload (every field optional).
    try:
        validated = _validate_user_body(body, partial=True)
    except ValidationError as exc:
        return _error("VALIDATION_ERROR", exc.message, 422, exc.details)

    # 4. Delegate to the domain layer.
    try:
        updated = business.update_user(_repo(), id, validated)
    except business.UserNotFound:
        return _error("NOT_FOUND", "User not found", 404)
    except business.EmailAlreadyExists:
        return _error(
            "EMAIL_ALREADY_EXISTS",
            "A user with this email already exists",
            409,
        )

    # 5. Success: 200 + serialized User body.
    return jsonify(_serialize_user(updated)), 200


# ---------------------------------------------------------------------------
# DELETE /api/v1/users/{id} — Delete a user by id (Task 15.1)
# ---------------------------------------------------------------------------
@api_blueprint.route("/api/v1/users/<id>", methods=["DELETE"])
def delete_user(id):
    """
    Delete a single user by its UUID.

    Flow (Requirements: REQ-USR-E06.1–3, REQ-USR-P01):

    1. Validate the ``{id}`` path parameter as a UUID v4 via
       :func:`_is_valid_uuid_v4` — a malformed id -> ``422 VALIDATION_ERROR``.
    2. Delegate to :func:`app.business.delete_user`; a syntactically valid but
       unknown id (including one already deleted) surfaces as ``UserNotFound``
       -> ``404 NOT_FOUND``.
    3. On success respond ``204 No Content`` with an empty body.
    """
    # 1. Validate the path parameter as a UUID v4.
    if not _is_valid_uuid_v4(id):
        return _error(
            "VALIDATION_ERROR",
            "Validation failed",
            422,
            {"id": "must be a valid UUID v4"},
        )

    # 2. Delegate to the domain layer.
    try:
        business.delete_user(_repo(), id)
    except business.UserNotFound:
        return _error("NOT_FOUND", "User not found", 404)

    # 3. Success: 204 No Content, no body.
    return "", 204
