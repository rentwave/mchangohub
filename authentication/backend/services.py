from authentication.models import Identity, LoginLog
from utils.service_base import ServiceBase


class IdentityService(ServiceBase):
    manager = Identity.objects


class LoginLogService(ServiceBase):
    manager = LoginLog.objects