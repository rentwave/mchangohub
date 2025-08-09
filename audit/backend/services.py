from audit.models import AuditLog
from utils.service_base import ServiceBase


class AuditLogService(ServiceBase):
    manager = AuditLog.objects