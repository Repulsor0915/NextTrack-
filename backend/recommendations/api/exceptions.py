from rest_framework.exceptions import ParseError, ValidationError
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    """Return one documented error envelope for all handled DRF errors."""

    response = exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, ParseError):
        code = "MALFORMED_JSON"
        message = "The request body is not valid JSON."
        details = {"parse_error": str(exc.detail)}
    elif isinstance(exc, ValidationError):
        code = "VALIDATION_ERROR"
        message = "Request validation failed. See details for specific fields."
        details = _plain(response.data)
    else:
        detail = response.data.get("detail") if isinstance(response.data, dict) else None
        code = str(
            getattr(detail, "code", getattr(exc, "default_code", "API_ERROR"))
        ).upper()
        message = str(detail or "The API request could not be completed.")
        details = {}

    response.data = {
        "error": {
            "code": code,
            "message": message,
            "details": details,
        }
    }
    return response


def _plain(value):
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return str(value)
