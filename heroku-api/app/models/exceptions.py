"""
Custom exception hierarchy for API error handling
7 exception classes with HTTP status code mapping
"""

from typing import Optional, Dict, Any


class ComplianceAPIException(Exception):
    """
    Base exception for all API errors.
    Includes HTTP status code and structured error context.
    """

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
        context: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize exception.

        Args:
            message: Human-readable error message
            status_code: HTTP status code
            error_code: Machine-readable error code
            context: Additional error context
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.context = context or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dict for JSON response"""
        return {
            "error": {
                "message": self.message,
                "code": self.error_code,
                "status": self.status_code,
                "context": self.context,
            }
        }


class ModelNotAvailableException(ComplianceAPIException):
    """
    AI model is unavailable or failed to respond.
    HTTP 503 Service Unavailable
    """

    def __init__(
        self,
        message: str = "AI model is currently unavailable",
        context: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            status_code=503,
            error_code="MODEL_UNAVAILABLE",
            context=context,
        )


class InvalidQueryException(ComplianceAPIException):
    """
    User query is malformed or invalid.
    HTTP 400 Bad Request
    """

    def __init__(
        self,
        message: str = "Invalid query format",
        context: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            status_code=400,
            error_code="INVALID_QUERY",
            context=context,
        )


class InsufficientPermissionsException(ComplianceAPIException):
    """
    User lacks required permissions for the operation.
    HTTP 403 Forbidden
    """

    def __init__(
        self,
        message: str = "Insufficient permissions for this operation",
        required_permission: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        context = context or {}
        if required_permission:
            context["required_permission"] = required_permission

        super().__init__(
            message=message,
            status_code=403,
            error_code="INSUFFICIENT_PERMISSIONS",
            context=context,
        )


class RateLimitExceededException(ComplianceAPIException):
    """
    User has exceeded their rate limit.
    HTTP 429 Too Many Requests
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
        limit: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        context = context or {}
        if retry_after:
            context["retry_after"] = retry_after
        if limit:
            context["limit"] = limit

        super().__init__(
            message=message,
            status_code=429,
            error_code="RATE_LIMIT_EXCEEDED",
            context=context,
        )

        self.retry_after = retry_after


class ExternalAPIException(ComplianceAPIException):
    """
    External API call failed (e.g., Grok-4, Redis).
    HTTP 502 Bad Gateway
    """

    def __init__(
        self,
        message: str = "External API call failed",
        service: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        context = context or {}
        if service:
            context["service"] = service

        super().__init__(
            message=message,
            status_code=502,
            error_code="EXTERNAL_API_ERROR",
            context=context,
        )


class ComplianceProcessingException(ComplianceAPIException):
    """
    Error during compliance query processing.
    HTTP 422 Unprocessable Entity
    """

    def __init__(
        self,
        message: str = "Failed to process compliance query",
        stage: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        context = context or {}
        if stage:
            context["stage"] = stage

        super().__init__(
            message=message,
            status_code=422,
            error_code="PROCESSING_ERROR",
            context=context,
        )