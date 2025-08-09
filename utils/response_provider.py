from django.http import JsonResponse


class ResponseProvider:
    @staticmethod
    def success(code="200.000", message="Success", data=None):
        return JsonResponse({
            "success": True,
            "code": code,
            "message": message,
            "data": data or {}
        }, status=200)

    @staticmethod
    def created(code="201.000", message="Created", data=None):
        return JsonResponse({
            "success": True,
            "code": code,
            "message": message,
            "data": data or {}
        }, status=201)

    @staticmethod
    def error(code="400.000", message="Error", error=None):
        return JsonResponse({
            "success": False,
            "code": code,
            "message": message,
            "error": error or ""
        }, status=400)

    @staticmethod
    def not_found(message="Not found", code="404.000"):
        return JsonResponse({
            "success": False,
            "code": code,
            "message": message
        }, status=404)

    @staticmethod
    def unauthorized(message="Not authenticated", code="401.000"):
        return JsonResponse({
            "success": False,
            "code": code,
            "message": message
        }, status=401)

    @staticmethod
    def forbidden(message="Forbidden", code="403.000"):
        return JsonResponse({
            "success": False,
            "code": code,
            "message": message
        }, status=403)

    @staticmethod
    def server_error(message="Server error", code="500.000"):
        return JsonResponse({
            "success": False,
            "code": code,
            "message": message
        }, status=500)
