import functools

from django.core.exceptions import PermissionDenied

from utils.response_provider import ResponseProvider


def user_login_required(required_permission=None):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(view, request, *args, **kwargs):
            user = request.user
            if not user or not user.is_authenticated:
                return ResponseProvider.unauthorized()

            if required_permission:
                perms = [required_permission] if isinstance(required_permission, str) else required_permission
                if not any(user.has_permission(perm) for perm in perms):
                    raise PermissionDenied()

            return func(view, request, *args, **kwargs)

        return wrapper

    if callable(required_permission):
        return decorator(required_permission)
    return decorator
