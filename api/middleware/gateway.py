import base64
import json
import logging
import re
import traceback
import uuid
from datetime import timedelta, datetime

from django.db.models import F, Q
from django.db.models.aggregates import Sum
from django.http import QueryDict
from django.urls import resolve
from django.utils import timezone
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import load_pem_public_key, load_pem_private_key
from cryptography.exceptions import InvalidSignature
from django.contrib.auth.models import AnonymousUser

from api.models import RateLimitRule, RateLimitAttempt, RateLimitBlock, ApiClient, SystemKey
from audit.backend.request_context import RequestContext
from audit.models import RequestLog
from authentication.backend.services import IdentityService
from utils.common import get_request_data
from utils.response_provider import ResponseProvider

logger = logging.getLogger(__name__)


class GatewayControlMiddleware:
    REQUIRED_HEADERS = ["X-Api-Key"]

    API_KEY_HEADER = "X-Api-Key"
    SIGNATURE_HEADER = "X-Signature"
    ENCRYPTED_HEADER = "X-Encrypted"

    API_CLIENT_VALIDATION_EXEMPT_PATHS = [
        "/console",
        "/health",
        "/static",
        "/media",
        "/__debug__",
        "/favicon.ico",
    ]

    SAVE_REQUEST_LOG_EXEMPT_PATHS = []

    ENCRYPTED = False

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/api/"):
            request._dont_enforce_csrf_checks = True

        self.ENCRYPTED = request.headers.get(self.ENCRYPTED_HEADER) == "1"
        if self.ENCRYPTED:
            request = self._decrypt_request_body(request)

        self._set_request_metadata(request)

        RequestContext.set(
            request=request,
            user=request.user if not isinstance(request.user, AnonymousUser) else None,
            token=request.token,
            is_authenticated=request.is_authenticated,
            ip_address=request.client_ip,
            user_agent=request.user_agent,
            request_id=str(uuid.uuid4()),
            request_data=request.data,
            session_key=getattr(request.session, 'session_key', None),
            request_method=request.method,
            request_path=request.path,
            is_secure=request.is_secure(),
            started_at=timezone.now(),
        )

        print(RequestContext.get())

        # missing = [h for h in self.REQUIRED_HEADERS if h not in request.headers]
        # if missing:
        #     response = JsonResponse(
        #         {"error": f"Missing required headers: {', '.join(missing)}"},
        #         status=400
        #     )
        #     return self._process_response(request, response)

        response = self._validate_api_client(request)
        RequestContext.update(api_client=request.api_client)
        if response:
            return self._process_response(request, response)

        response = self._verify_signature_if_present(request)
        if response:
            return self._process_response(request, response)

        rate_limit_result = self._check_rate_limit(request)
        if rate_limit_result.get("blocked"):
            response = ResponseProvider.too_many_requests(error="Rate limit exceeded. Try again later.")
            response = self._set_headers(response, rate_limit_result)
            return self._process_response(request, response)

        # noinspection PyBroadException
        try:
            resolver_match = resolve(request.path)
            view_func = resolver_match.func
            self._process_view(request, view_func, resolver_match.args, resolver_match.kwargs)
        except:
            pass

        response = self.get_response(request)
        response = self._set_headers(response, rate_limit_result)
        return self._process_response(request, response)

    @staticmethod
    def _process_view(request, view_func, view_args, view_kwargs):
        view_name = getattr(view_func, '__name__', 'unknown')
        RequestContext.update(
            view_name=view_name,
            view_args=view_args,
            view_kwargs=view_kwargs,
        )

    def process_exception(self, request, exception):
        logger.error(
            "Unhandled exception\n"
            f"Path: {request.path}\n"
            f"Method: {request.method}\n"
            f"User: {getattr(request.user, 'username', 'Anonymous')}\n"
            f"Exception Type: {type(exception).__name__}\n"
            f"Message: {str(exception)}\n"
            f"Traceback:\n{traceback.format_exc()}"
        )
        RequestContext.update(
            exception_type=type(exception).__name__,
            exception_message=str(exception),
        )
        response = ResponseProvider.handle_exception(exception)
        return self._process_response(request, response)

    def _process_response(self, request, response):
        if hasattr(response, 'status_code'):
            RequestContext.update(response_status=response.status_code)

        # noinspection PyBroadException
        try:
            if hasattr(response, 'data'):
                response_data = response.data
            elif hasattr(response, 'content') and response.get('Content-Type', '').startswith('application/json'):
                response_data = json.loads(response.content)
            else:
                response_data = getattr(response, 'content', '')
                if isinstance(response_data, bytes):
                    response_data = response_data.decode(errors='ignore')
                response_data = response_data[:2000]
        except:
            response_data = f'<Could not parse response: {type(response).__name__}>'

        RequestContext.update(response_data=response_data)
        self._save_request_log()
        RequestContext.clear()

        if self.ENCRYPTED:
            response = self._encrypt_response(response)

        return response

    def _set_request_metadata(self, request):
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.split(" ", 1)[1].strip() if auth_header.startswith("Bearer ") else None

        user = getattr(request, 'user', None)
        if user and not isinstance(user, AnonymousUser):
            is_authenticated = True
        else:
            is_authenticated, user = self._check_if_user_authenticated(token)

        request.token = token
        request.user = user
        request.is_authenticated = is_authenticated
        request.client_ip = self._get_client_ip(request)
        request.user_agent = request.headers.get("User-Agent", "")
        request.data, request.files = get_request_data(request)
        request.received_at = timezone.now()

    @staticmethod
    def _get_client_ip(request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')

    @staticmethod
    def _check_if_user_authenticated(token):
        if not token:
            return False, AnonymousUser()

        identity = (
            IdentityService()
            .filter(~Q(user=None), token=token, state__name="Active")
            .order_by("-date_created")
            .first()
        )

        if not identity:
            return False, AnonymousUser()

        identity.extend()
        return True, identity.user

    def _validate_api_client(self, request):
        request.api_client = None
        if any(request.path.startswith(p) for p in self.API_CLIENT_VALIDATION_EXEMPT_PATHS):
            return None

        api_key = request.headers.get(self.API_KEY_HEADER)
        if not api_key:
            return ResponseProvider.unauthorized(error="Missing API key")

        client = ApiClient.objects.filter(api_key=api_key, is_active=True).first()
        if not client:
            logger.warning("Invalid API key attempted from IP %s", request.client_ip)
            return ResponseProvider.unauthorized(error="Invalid API key")

        if client.allowed_ips:
            allowed = [ip.strip() for ip in client.allowed_ips.split(",") if ip.strip()]
            if request.client_ip not in allowed:
                logger.warning("IP %s not allowed for client %s", request.client_ip, client.name)
                return ResponseProvider.forbidden(error="IP address not allowed")

        request.api_client = client
        return None

    def _verify_signature_if_present(self, request):
        signature_b64 = request.headers.get(self.SIGNATURE_HEADER)
        if not signature_b64:
            return None

        client = getattr(request, "api_client", None)
        if not client:
            return ResponseProvider.forbidden(error= "Client context missing for signature verification")

        client_key = client.get_active_public_key()
        if not client_key or not client_key.public_key:
            logger.warning("No active public key for client %s", client.name)
            return ResponseProvider.server_error(error="Client public key not configured")

        try:
            public_key = load_pem_public_key(client_key.public_key.encode("utf-8"))
            signature = base64.b64decode(signature_b64)
            body_bytes = getattr(request, "body", b"")

            public_key.verify(
                signature,
                body_bytes,
                asym_padding.PSS(
                    mgf=asym_padding.MGF1(hashes.SHA256()),
                    salt_length=asym_padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
        except InvalidSignature:
            logger.warning("Invalid signature from client %s (IP %s)", client.name, request.client_ip)
            return ResponseProvider.unauthorized(error="Invalid signature")
        except Exception as exc:
            logger.exception("Signature verification error for client %s: %s", client.name, exc)
            return ResponseProvider.server_error(error="Signature verification failed")

        return None

    @staticmethod
    def _get_window_start(now, window):
        seconds = int(window.total_seconds())
        timestamp = int(now.timestamp())
        bucket = timestamp - (timestamp % seconds)
        return datetime.fromtimestamp(bucket, tz=timezone.get_current_timezone())

    def _check_rate_limit(self, request) -> dict:
        client_ip = getattr(request, "client_ip", None)
        api_client_id = str(request.api_client.id) if getattr(request, "api_client", None) else f"anon-{client_ip}"
        user_id = str(request.user.id) if getattr(request, "user", None) else f"anon-{client_ip}"
        endpoint = request.path
        method = request.method
        now = timezone.now()

        rules = RateLimitRule.objects.filter(is_active=True).order_by("-priority")

        most_restrictive_info = {
            "blocked": False,
            "limit": 0,
            "remaining": float("inf"),
            "reset": 0
        }

        for rule in rules:
            if rule.endpoint_pattern and not re.match(rule.endpoint_pattern, endpoint):
                continue

            limit_key = self._make_limit_key(rule.scope, api_client_id, user_id, client_ip, endpoint)
            window = rule.get_period_timedelta()
            window_start = self._get_window_start(now, window)

            block = RateLimitBlock.objects.filter(
                rule=rule,
                key=limit_key,
                blocked_until__gt=now
            ).first()
            if block:
                retry_after = int((block.blocked_until - now).total_seconds())
                return {
                    "blocked": True,
                    "limit": rule.limit,
                    "remaining": 0,
                    "reset": int(block.blocked_until.timestamp()),
                    "retry_after": retry_after
                }

            attempt, created = RateLimitAttempt.objects.get_or_create(
                rule=rule,
                key=limit_key,
                endpoint=endpoint,
                window_start=window_start,
                defaults={"count": 0, "method": method, "last_attempt": now}
            )
            RateLimitAttempt.objects.filter(pk=attempt.pk).update(count=F("count") + 1)

            total_attempts = RateLimitAttempt.objects.filter(
                rule=rule,
                key=limit_key,
                window_start=window_start
            ).aggregate(total=Sum("count"))["total"] or 0

            if total_attempts > rule.limit:
                reset_time = window_start + window
                blocked_until = reset_time
                if rule.block_duration_minutes > 0:
                    extra = now + timedelta(minutes=rule.block_duration_minutes)
                    blocked_until = max(reset_time, extra)

                RateLimitBlock.objects.update_or_create(
                    rule=rule,
                    key=limit_key,
                    defaults={"blocked_until": blocked_until}
                )

                return {
                    "blocked": True,
                    "limit": rule.limit,
                    "remaining": 0,
                    "reset": int(reset_time.timestamp()),
                    "retry_after": int((blocked_until - now).total_seconds())
                }

            remaining = max(0, rule.limit - attempt.count)
            if remaining < most_restrictive_info["remaining"]:
                most_restrictive_info = {
                    "blocked": False,
                    "limit": rule.limit,
                    "remaining": remaining,
                    "reset": int((window_start + window).timestamp())
                }

        if most_restrictive_info["remaining"] == float("inf"):
            most_restrictive_info["remaining"] = -1

        return most_restrictive_info

    @staticmethod
    def _make_limit_key(scope, api_client_id, user_id, client_ip, endpoint, endpoint_pattern=None):
        if scope == "global":
            return "global"
        if scope == "api_client":
            if endpoint_pattern:
                return f"api_client{api_client_id}:endpoint:{endpoint}"
            return f"api_client:{api_client_id}"
        if scope == "user":
            if endpoint_pattern:
                return f"user:{user_id}:endpoint:{endpoint}"
            return f"user:{user_id}"
        if scope == "ip":
            if endpoint_pattern:
                return f"ip:{client_ip}:endpoint:{endpoint}"
            return f"ip:{client_ip}"
        if scope == "endpoint":
            return f"endpoint:{endpoint}"
        if scope == "user_endpoint":
            return f"user:{user_id}:endpoint:{endpoint}"
        if scope == "ip_endpoint":
            return f"ip:{client_ip}:endpoint:{endpoint}"
        return "unknown"

    @staticmethod
    def _load_system_keys():
        try:
            system_key = SystemKey.objects.filter(is_active=True).order_by("-date_created").first()
            if not system_key:
                logger.error("No active system key found in database.")
                return None, None

            priv_key_obj = load_pem_private_key(system_key.private_key.encode("utf-8"), password=None)
            pub_key_obj = load_pem_public_key(system_key.public_key.encode("utf-8"))
            return priv_key_obj, pub_key_obj
        except Exception as e:
            logger.exception("Failed to load system keys from database: %s", e)
            return None, None

    def encrypt_payload(self, data):
        plaintext = json.dumps(data).encode("utf-8")
        _, pub_key_obj = self._load_system_keys()
        if not pub_key_obj:
            raise RuntimeError("No system public key available for encryption")

        return pub_key_obj.encrypt(
            plaintext,
            asym_padding.OAEP(
                mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

    def decrypt_payload(self, ciphertext):
        priv_key_obj, _ = self._load_system_keys()
        if not priv_key_obj:
            raise RuntimeError("No system private key available for decryption")

        plaintext = priv_key_obj.decrypt(
            ciphertext,
            asym_padding.OAEP(
                mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        return json.loads(plaintext.decode("utf-8"))

    def _decrypt_request_body(self, request):
        try:
            if request.body:
                ciphertext = base64.b64decode(request.body)
                decrypted_data = self.decrypt_payload(ciphertext)
                request._body = json.dumps(decrypted_data).encode("utf-8")
                request.POST = QueryDict('', mutable=True)
        except Exception as e:
            logger.warning(f"Failed to decrypt request body: {e}")
        return request

    def _encrypt_response(self, response):
        try:
            if hasattr(response, "content") and response.get("Content-Type", "").startswith("application/json"):
                raw_content = json.loads(response.content)
                ciphertext = self.encrypt_payload(raw_content)
                encrypted_b64 = base64.b64encode(ciphertext).decode("utf-8")
                response.content = json.dumps(encrypted_b64).encode("utf-8")
                response["Content-Length"] = str(len(response.content))
        except Exception as e:
            logger.warning(f"Failed to encrypt response body: {e}")
        return response

    @staticmethod
    def _set_headers(response, rate_limit_info=None):
        if rate_limit_info and rate_limit_info.get("limit") is not None:
            response["X-RateLimit-Limit"] = str(rate_limit_info["limit"])
            response["X-RateLimit-Remaining"] = str(rate_limit_info["remaining"])
            response["X-RateLimit-Reset"] = str(rate_limit_info["reset"])
            if rate_limit_info.get("retry_after"):
                response["Retry-After"] = str(rate_limit_info["retry_after"])
        return response

    def _save_request_log(self):
        try:
            ctx = RequestContext.get()

            path = ctx.get('request_path', '')
            if any(path.startswith(ep) for ep in self.SAVE_REQUEST_LOG_EXEMPT_PATHS):
                return

            started_at = ctx.get('started_at')
            ended_at = timezone.now()
            time_taken = (ended_at - started_at).total_seconds()

            RequestLog.objects.create(
                request_id=ctx.get('request_id'),
                api_client=ctx.get('api_client'),
                user=ctx.get('user'),
                token=ctx.get('token'),
                is_authenticated=ctx.get('is_authenticated', False),
                ip_address=ctx.get('ip_address'),
                user_agent=ctx.get('user_agent', ''),
                session_key=ctx.get('session_key'),
                request_method=ctx.get('request_method'),
                request_path=ctx.get('request_path'),
                request_data=ctx.get('request_data'),
                is_secure=ctx.get('is_secure', False),
                view_name=ctx.get('view_name'),
                view_args=ctx.get('view_args'),
                view_kwargs=ctx.get('view_kwargs'),
                activity_name=ctx.get('activity_name'),
                exception_type=ctx.get('exception_type'),
                exception_message=ctx.get('exception_message'),
                started_at=started_at,
                ended_at=ended_at,
                time_taken=time_taken,
                response_status=ctx.get('response_status'),
                response_data=ctx.get('response_data'),
            )
        except Exception as e:
            logger.exception(f"Failed to save RequestLog: {e}")
