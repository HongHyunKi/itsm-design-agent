from typing import Any


class AppError(Exception):
    """모든 도메인 예외의 기반. main.py 핸들러가 {code, message, detail} JSON으로 바꿉니다."""

    status_code = 500
    code = "internal_error"
    message = "Internal server error"

    def __init__(
        self,
        message: str | None = None,
        detail: Any = None,
        *,
        status_code: int | None = None,
        code: str | None = None,
    ) -> None:
        self.message = message or self.message
        self.detail = detail
        self.status_code = status_code or self.status_code
        self.code = code or self.code
        super().__init__(self.message)


class NotFound(AppError):
    status_code = 404
    code = "not_found"
    message = "Resource not found"


class AuthFailed(AppError):
    status_code = 401
    code = "auth_failed"
    message = "Authentication failed"


class PermissionDenied(AppError):
    status_code = 403
    code = "permission_denied"
    message = "Permission denied"


class ValidationFailed(AppError):
    status_code = 422
    code = "validation_failed"
    message = "Validation failed"


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"
    message = "Too many requests"
