import inspect
import logging

from functools import wraps

from django.core.handlers.wsgi import WSGIRequest
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from audit.backend.audit_management_service import AuditManagementService
from authentication.backend.services import IdentityService
from authentication.models import Identity
from utils.common import get_request_data
from utils.response_provider import ResponseProvider

logger = logging.getLogger(__name__)

def request_handler(_func=None, *, user_login_required=True, audit=False, audit_action=None):
    def decorator(func):
        @wraps(func)
        @csrf_exempt
        def wrapper(*args, **kwargs):
            try:
                request = None
                self_instance = None

                # Find the WSGIRequest object and self instance if among the arguments
                for arg in args:
                    if isinstance(arg, WSGIRequest):
                        request = arg
                    elif self_instance is None and hasattr(arg, "__class__"):
                        self_instance = arg

                if not request:
                    raise Exception("No request object found")

                # Extract headers
                token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
                source_ip = request.headers.get("X-Source-IP") or request.META.get("REMOTE_ADDR", "")

                # Attach to request
                request.token = token
                request.source_ip = source_ip

                # Parse data and files
                data, files = get_request_data(request)
                request.data = data
                request.files = files

                authenticated = False
                request.user = None

                # Get request user and system if token is provided
                if request.token:
                    identity = IdentityService().filter(
                        token=token,
                        status=Identity.Status.ACTIVE,
                        expires_at__gte=timezone.now()
                    ).first()
                    if identity is not None:
                        authenticated = True
                        request.user = identity.user
                        identity.extend()

                # Optionally audit the request
                audit_log = None
                if audit:
                    action = audit_action or func.__name__
                    audit_log = AuditManagementService().start_log(request=request, action=action)

                # Optional authenticate user
                if user_login_required:
                    if not authenticated:
                        response = ResponseProvider.unauthorized()
                        if audit_log:
                            AuditManagementService().complete_log(log=audit_log, response=response)
                        return response

                # Dynamically map arguments
                sig = inspect.signature(func)
                param_names = list(sig.parameters.keys())
                call_args = []

                for param in param_names:
                    if param == "self":
                        call_args.append(self_instance)
                    elif param == "request":
                        call_args.append(request)
                    elif param in kwargs:
                        call_args.append(kwargs[param])
                    else:
                        call_args.append(None)

                response = func(*call_args)

                # Ensure response is a JsonResponse
                if not isinstance(response, JsonResponse):
                    response = JsonResponse(response)

                # Complete audit log
                if audit_log:
                    AuditManagementService().complete_log(log=audit_log, response=response)

                return response

            except Exception as e:
                logger.exception("request_handler decorator exception: %s", str(e))
                return ResponseProvider.server_error()

        return wrapper

    # If used like @request_handler without parentheses
    if _func is not None and callable(_func):
        return decorator(_func)

    return decorator

