from django.core.exceptions import ValidationError, ObjectDoesNotExist, PermissionDenied
from django.http import JsonResponse


class ResponseProvider:
    @staticmethod
    def _response(success: bool, code: str, message: str, status: int, data=None, error=None) -> JsonResponse:
        return JsonResponse({
            'success': success,
            'code': code,
            'message': message,
            'data': data or {},
            'error': error or '',
        }, status=status)

    @classmethod
    def handle_exception(cls, ex: Exception) -> JsonResponse:
        if isinstance(ex, ValidationError):
            if hasattr(ex, "messages"):
                error_message = ", ".join(ex.messages)
            else:
                error_message = str(ex)
            return cls.bad_request(message="Validation Error", error=error_message)
        elif isinstance(ex, ObjectDoesNotExist):
            return cls.not_found(error=str(ex))
        elif isinstance(ex, PermissionDenied):
            return cls.forbidden(error=str(ex))
        else:
            return cls.server_error(error=str(ex))

    @classmethod
    def success(cls, code='200.000', message='Success', data=None):
        return cls._response(True, code, message, 200, data=data)

    @classmethod
    def created(cls, code="201.000", message='Created', data=None):
        return cls._response(True, code, message, 201, data=data)

    @classmethod
    def accepted(cls, code="202.000", message='Accepted', data=None):
        return cls._response(True, code, message, 202, data=data)

    @classmethod
    def bad_request(cls, code="400.000", message='Bad Request', error=None):
        return cls._response(False, code, message, 400, error=error)

    @classmethod
    def unauthorized(cls, code="401.000", message='Unauthorized', error=None):
        return cls._response(False, code, message, 401, error=error)

    @classmethod
    def forbidden(cls, code="403.000", message='Forbidden', error=None):
        return cls._response(False, code, message, 403, error=error)

    @classmethod
    def not_found(cls, code="404.000", message='Resource Not Found', error=None):
        return cls._response(False, code, message, 404, error=error)

    @classmethod
    def too_many_requests(cls, code="429.000", message='Rate Limit Exceeded', error=None):
        return cls._response(False, code, message, 429, error=error)

    @classmethod
    def server_error(cls, code="500.000", message='Internal Server Error', error=None):
        return cls._response(False, code, message, 500, error=error)

    @classmethod
    def not_implemented(cls, code="501.000", message='Not Implemented', error=None):
        return cls._response(False, code, message, 501, error=error)

    @classmethod
    def service_unavailable(cls, code="503.000", message='Service Unavailable', error=None):
        return cls._response(False, code, message, 503, error=error)
