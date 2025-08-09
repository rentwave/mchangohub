import json
import logging

from django.http import JsonResponse

from audit.backend.services import AuditLogService
from audit.models import AuditLog
from utils.common import sanitize_data

logger = logging.getLogger(__name__)


class AuditManagementService:
    @staticmethod
    def start_log(request, action: str) -> AuditLog | None:
        """
        Create an initial audit log entry based on the request metadata.

        :param request: Django request object containing request context
        :param action: Name of the action being audited
        :return: AuditLog instance if created successfully, else None
        :rtype: AuditLog | None
        :raises Exception: Logs any exceptions during log creation
        """
        try:
            log = AuditLogService().create(
                action=action,
                api_client=getattr(request, "api_client", None),
                user=getattr(request, "user", None),
                system=getattr(request, "system", None),
                ip_address=getattr(request, "source_ip", None),
                request_path=request.path,
                request_method=request.method,
                request_data=sanitize_data(getattr(request, "data", {})),
            )
            return log
        except Exception as ex:
            logger.exception(f"AuditManagementService - start_log exception: {ex}")
            return None

    @staticmethod
    def complete_log(log: AuditLog, response: JsonResponse) -> AuditLog | None:
        """
        Finalize an audit log entry with response details.

        :param log: Existing AuditLog instance to be updated
        :param response: Django JsonResponse object returned by the view
        :return: Updated AuditLog instance if successful, else None
        :rtype: AuditLog | None
        :raises Exception: Logs any exceptions during log completion
        """
        try:
            response_data = json.loads(response.content)
            log.response_data = sanitize_data(response_data)
            log.response_status_code = response.status_code
            log.successful = 200 <= response.status_code < 300
            log.save()
            return log
        except Exception as ex:
            logger.exception(f"AuditManagementService - complete_log exception: {ex}")
            return None
