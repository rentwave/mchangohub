import logging

from otps.backend.otp_management_service import OTPManagementService
from utils.response_provider import ResponseProvider

logger = logging.getLogger(__name__)


class OTPAPIHandler:
    @staticmethod
    def send_otp(request):
        """
        Sends a one-time password (OTP) to a user.

        :param request: Django HTTP request object containing 'purpose', 'delivery_method', 'contact', and
         optional 'user_id'.
        :type request: HttpRequest
        :return: JSON response with status code, message, and success status.
        :rtype: JsonResponse
        :raises Exception: On OTP sending failure.
        """
        purpose = request.data.get("purpose", "")
        delivery_method = request.data.get("delivery_method", "")
        contact = request.data.get("contact", "")
        user = request.user
        token = request.token

        OTPManagementService().send_otp(
            purpose=purpose,
            delivery_method=delivery_method,
            contact=contact,
            user=user,
            token=token
        )
        return ResponseProvider.success(message="OTP sent successfully")

    @staticmethod
    def verify_otp(request):
        """
        Verifies a one-time password (OTP) provided by the user.

        :param request: Django HTTP request object containing 'purpose', 'code', 'contact', and optional 'user_id'.
        :type request: HttpRequest
        :return: JSON response with status code, message, and success status.
        :rtype: JsonResponse
        :raises Exception: On OTP verification failure.
        """
        purpose = request.data.get("purpose", "")
        code = request.data.get("code", "")
        contact = request.data.get("contact", "")
        user = request.user
        token = request.token

        OTPManagementService().verify_otp(
            purpose=purpose,
            code=code,
            contact=contact,
            user=user,
            token=token
        )
        return ResponseProvider.success(message="OTP verified successfully")
