from api.models import (
    ApiClient,
    ApiClientKey,
    SystemKey,
    APICallback,
    RateLimitRule,
    RateLimitAttempt,
    RateLimitBlock
)
from utils.service_base import ServiceBase


class APIClientService(ServiceBase):
    manager = ApiClient.objects


class ApiClientKeyService(ServiceBase):
    manager = ApiClientKey.objects


class SystemKeyService(ServiceBase):
    manager = SystemKey.objects


class APICallbackService(ServiceBase):
    manager = APICallback.objects


class RateLimitRuleService(ServiceBase):
    manager = RateLimitRule.objects


class RateLimitAttemptService(ServiceBase):
    manager = RateLimitAttempt.objects


class RateLimitBlockService(ServiceBase):
    manager = RateLimitBlock.objects