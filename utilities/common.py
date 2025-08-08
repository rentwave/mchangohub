import logging
import json
import random
import string

from django.core.handlers.wsgi import WSGIRequest

logger = logging.getLogger(__name__)

def get_request_data(request: WSGIRequest) -> tuple[dict, dict]:
    """
    Extracts structured data and uploaded files from a Django request.

    :param request: The Django WSGIRequest object.
    :return: A tuple containing:
        - data (dict): Parsed request data.
        - files (dict): Uploaded files keyed by field name.
    :raises: None. Returns empty dicts on error.
    :rtype: tuple[dict, dict]
    """
    try:
        if request is None:
            return {}, {}

        method = request.method
        content_type = request.META.get('CONTENT_TYPE', '')

        data = {}
        files = {}

        if 'application/json' in content_type:
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                data = {}
        elif method in ['POST', 'PUT', 'PATCH']:
            data = request.POST.dict()
        elif method == 'GET':
            data = request.GET.dict()

        if request.FILES:
            files = {
                key: request.FILES.getlist(key) if len(request.FILES.getlist(key)) > 1
                else request.FILES[key]
                for key in request.FILES
            }

        if not data and request.body:
            # noinspection PyBroadException
            try:
                data = json.loads(request.body)
            except Exception:
                data = {}

        return data, files

    except Exception as ex:
        logger.exception('get_request_data Exception: %s' % ex)
        return {}, {}


def generate_random_password(length=8):
    """
    Generates an alphanumeric password of specified length.

    :param length: Desired password length (>= 6).
    :type length: int
    :return: Generated password.
    :rtype: str
    :raises ValueError: If length is less than 6.
    """
    if length < 6:
        raise ValueError("Password length must be at least 6 characters.")
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))


def sanitize_data(data: dict) -> dict:
    """
    Redact sensitive fields in a dictionary by masking their values.

    This function replaces the values of known sensitive keys with '****'.

    :param data: Dictionary containing request or user data
    :return: A new dictionary with sensitive values masked
    :rtype: dict
    """
    sensitive_keys = {"password", "old_password", "new_password", "pin"}
    return {
        k: ("****" if k.lower() in sensitive_keys else v)
        for k, v in data.items()
    }