from __future__ import annotations


class TaskControlError(Exception):
    code = "INTERNAL_ERROR"
    status_code = 500

    def __init__(self, message: str, *, details: list[dict] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or []


class ValidationError(TaskControlError):
    code = "VALIDATION_ERROR"
    status_code = 422


class NotFoundError(TaskControlError):
    code = "NOT_FOUND"
    status_code = 404


class ConflictError(TaskControlError):
    code = "CONFLICT_VERSION"
    status_code = 409


class AuthError(TaskControlError):
    code = "AUTH_REQUIRED"
    status_code = 401


class InvalidCredentialsError(TaskControlError):
    code = "AUTH_INVALID_CREDENTIALS"
    status_code = 401


class AccountLockedError(TaskControlError):
    code = "AUTH_LOCKED"
    status_code = 423


class ForbiddenError(TaskControlError):
    code = "FORBIDDEN"
    status_code = 403


class RateLimitedError(TaskControlError):
    code = "RATE_LIMITED"
    status_code = 429

    def __init__(self, message: str, *, retry_after: int = 60) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class DefinitionDisabledError(TaskControlError):
    code = "DEFINITION_DISABLED"
    status_code = 409


class TargetDisabledError(TaskControlError):
    code = "TARGET_DISABLED"
    status_code = 409


class InvalidStateError(TaskControlError):
    code = "INVALID_STATE"
    status_code = 409


class PreconditionRequiredError(TaskControlError):
    code = "PRECONDITION_REQUIRED"
    status_code = 428
