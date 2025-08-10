import logging
import json
import random
import string

from django.conf import settings
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


def generate_random_pin(length=4):
    """
    Generates a numeric PIN of specified length.

    :param length: Length of the PIN (between 4 and 6).
    :type length: int
    :return: Numeric PIN.
    :rtype: str
    :raises ValueError: If length is not between 4 and 6.
    """
    if not 4 <= length <= 6:
        raise ValueError("PIN length must be between 4 and 6 digits.")
    return ''.join(random.choices(string.digits, k=length))


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


def normalize_phone_number(phone, country_code=None, total_count=None):
    """
    Normalize a phone number ensuring that:
        - it has a valid country code
        - required number of characters
        - all characters are digits
    @param phone: The phone number passed to be normalized
    @type phone: str
    @param country_code: The country code for the phone
    @type country_code: str
    @param total_count: The total digits required
	@type total_count: int
	@return: a normalized phone number
    @rtype: str
    """
    try:
        if country_code is None:
            country_code = settings.DEFAULT_COUNTRY_CODE
        if total_count is None:
            total_count = settings.PHONE_NUMBER_LENGTH
        phone = phone.replace(" ", "").replace('(', '').replace(')', '').replace('-', '')
        if str(phone).startswith('+'):
            phone = str(phone)[1:]
        if len(phone) == total_count:
            return phone
        elif (len(phone) + len(country_code)) == total_count:
            return str(country_code) + str(phone)
        elif str(phone).startswith('0') and ((len(phone) - 1) + len(country_code)) == total_count:
            return str(country_code) + str(phone)[1:]
        else:
            if len(country_code) > 0:
                overlap = abs((len(phone) + len(country_code)) - total_count)
                return str(country_code) + str(phone)[overlap - 1:]
            else:
                return phone
    except Exception as ex:
        print('normalize_phone_number Exception: %s', ex)
    return ''


def set_fields(fields, kwargs, instance=None):
    """
    Build and return a dictionary of field values from `kwargs` or `instance`.

    For each field in `fields`:
      - Value is taken from `kwargs` first.
      - If not provided, falls back to `instance` attribute or dict key.
      - If a transform function is provided for that field, it's applied before setting.
      - Empty strings and None values are ignored.

    :param fields: Iterable of field names OR dict {field_name: transform_function}.
                   If list/tuple, no transformation is applied.
                   If dict, each value should be a callable for transforming the field value.
    :type fields: list[str] | tuple[str] | dict[str, callable]
    :param kwargs: Source dictionary for incoming values.
    :type kwargs: dict
    :param instance: Optional model instance or dictionary to fall back on.
    :type instance: object | dict, optional
    :return: A new dictionary containing the populated fields.
    :rtype: dict
    """
    # If fields is a list/tuple, make all transforms identity functions
    if isinstance(fields, (list, tuple)):
        fields = {field: (lambda v: v) for field in fields}

    data = {}
    for field_name, transform in fields.items():
        # Get from kwargs first
        value = kwargs.get(field_name, None)

        # Fallback to instance
        if value is None and instance is not None:
            if isinstance(instance, dict):
                value = instance.get(field_name, None)
            else:
                value = getattr(instance, field_name, None)

        # Only set if not None or empty string
        if value not in (None, ""):
            data[field_name] = transform(value)

    return data
