import json

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.http import HttpResponse


class ApiRequestSizeMiddleware:
    """Reject oversized API payloads before parsing or writing anything."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._is_api_write(request):
            try:
                content_length = int(request.META.get("CONTENT_LENGTH", "0"))
            except (TypeError, ValueError):
                content_length = 0
            if content_length > settings.DATA_UPLOAD_MAX_MEMORY_SIZE:
                return self._too_large()
        return self.get_response(request)

    def process_exception(self, request, exception):
        if self._is_api_write(request) and isinstance(exception, RequestDataTooBig):
            return self._too_large()
        return None

    @staticmethod
    def _is_api_write(request):
        return request.path.startswith("/api/v1/") and request.method in {
            "POST", "PATCH", "PUT",
        }

    @staticmethod
    def _too_large():
        body = {
            "error": {
                "code": "REQUEST_TOO_LARGE",
                "message": "Request body exceeds the configured size limit.",
                "details": {},
            }
        }
        return HttpResponse(
            json.dumps(body), status=413, content_type="application/json"
        )
