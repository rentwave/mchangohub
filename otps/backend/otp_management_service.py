import hashlib
from datetime import timedelta
from random import randint

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from authentication.backend.services import IdentityService
from authentication.models import Identity
from notifications.backend.notification_management_service import NotificationManagementService
from otps.backend.services import OTPService
from otps.models import OTP
from users.backend.services import UserService


class OTPManagementService:
    @staticmethod
    def generate_raw_code(otp_length: int = 4) -> str:
        """
        Generate a random numeric OTP code of a given length.

        :param otp_length: The number of digits in the OTP.
        :type otp_length: int
        :return: A randomly generated numeric OTP code as a string.
        :rtype: str
        :raises ValueError: If the length is less than 1.
        """
        if otp_length < 1:
            raise ValueError("OTP length must be at least 1")

        lower_bound = 10 ** (otp_length - 1)
        upper_bound = (10 ** otp_length) - 1

        return str(randint(lower_bound, upper_bound))

    @staticmethod
    def hash_code(raw_code: str) -> str:
        """
        Hash the raw OTP code using SHA-256.

        :param raw_code: The raw OTP code.
        :type raw_code: str
        :return: A SHA-256 hash of the OTP code.
        :rtype: str
        """
        return hashlib.sha256(raw_code.encode()).hexdigest()

    @transaction.atomic
    def send_otp(
            self,
            purpose: str,
            delivery_method: str,
            contact: str = "",
            user_id: str = "",
            token: str = "",
    ) -> OTP:
        """
        Generate and send an OTP for a given purpose, delivery method, and user/contact.

        :param purpose: The purpose for the OTP (must be a valid OTP.PurposeTypes).
        :type purpose: str
        :param delivery_method: How the OTP should be sent (e.g., SMS or EMAIL).
        :type delivery_method: str
        :param contact: Optional phone number or email to send the OTP to.
        :type contact: str
        :param user_id: Optional user ID to whom the OTP is related.
        :type user_id: str
        :param token: Optional identity token for 2FA OTPs.
        :type token: str
        :return: The created OTP object.
        :rtype: OTP
        :raises ValueError: If required parameters are missing or invalid.
        :raises Exception: If identity, user, or OTP creation fails.
        """
        if purpose not in OTP.PurposeTypes.values:
            raise ValueError("Invalid purpose")

        identity = None
        if purpose == OTP.PurposeTypes.TWO_FACTOR_AUTHENTICATION:
            if not token:
                raise ValueError("Token must be provided for 2FA purpose")
            identity = IdentityService().filter(
                token=token,
                status=Identity.Status.ACTIVATION_PENDING,
                expires_at__gte=timezone.now(),
            ).first()
            if identity is None:
                raise Exception("Identity not found")

        if delivery_method not in OTP.DeliveryMethods.values:
            raise ValueError("Invalid delivery method")

        user = None
        if user_id:
            user = UserService().get(id=user_id, is_active=True)
            if user is None:
                raise Exception("User not found")

        if not contact:
            if not user:
                raise ValueError("Either contact or valid user must be provided.")
            contact = user.email if delivery_method == "EMAIL" else user.phone_number
            if not contact:
                raise Exception("Contact not found")

        raw_code = self.generate_raw_code(settings.OTP_LENGTH)
        hashed_code = self.hash_code(raw_code)

        expires_at = timezone.now() + timedelta(
            seconds=settings.OTP_VALIDITY_SECONDS if purpose == OTP.PurposeTypes.TWO_FACTOR_AUTHENTICATION
            else settings.ACTION_OTP_VALIDITY_SECONDS
        )

        otp = OTPService().create(
            user=user,
            purpose=purpose,
            identity=identity,
            delivery_method=delivery_method,
            contact=contact,
            code=hashed_code,
            expires_at=expires_at
        )
        if otp is None:
            raise Exception("OTP not created due to a database exception")

        NotificationManagementService(user).send_notification(
            delivery_method=delivery_method,
            template=f"{delivery_method.lower()}_otp",
            context={"otp": raw_code},
        )

        return otp

    @transaction.atomic
    def verify_otp(
            self,
            purpose: str,
            code: str,
            contact: str = "",
            user_id: str = "",
            token: str = "",
    ) -> OTP:
        """
        Validate and mark an OTP as used.

        :param purpose: The purpose of the OTP (must match OTP.PurposeTypes).
        :type purpose: str
        :param code: The OTP code input by the user.
        :type code: str
        :param contact: Optional contact address (phone or email).
        :type contact: str
        :param user_id: Optional user ID associated with the OTP.
        :type user_id: str
        :param token: Optional identity token (used in 2FA).
        :type token: str
        :return: The verified OTP object.
        :rtype: OTP
        :raises ValueError: If validation fails.
        :raises Exception: If user or the identity is not found.
        """
        if not code:
            raise ValueError("OTP code must be provided")

        if purpose not in OTP.PurposeTypes.values:
            raise ValueError("Invalid purpose")

        user = UserService().get(id=user_id, is_active=True) if user_id else None
        if user_id and user is None:
            raise Exception("User not found")

        identity = None
        if purpose == OTP.PurposeTypes.TWO_FACTOR_AUTHENTICATION:
            if not token:
                raise ValueError("Token must be provided for 2FA purpose")
            identity = IdentityService().get(token=token, expires_at__gte=timezone.now())
            if identity is None:
                raise Exception("Identity not found or expired")

        if not purpose == OTP.PurposeTypes.TWO_FACTOR_AUTHENTICATION:
            if not user and not contact:
                raise ValueError("Either user_id or contact must be provided ")

        filter_params = {
            "is_used": False,
            "expires_at__gte": timezone.now(),
            "purpose": purpose
        }
        if user:
            filter_params["user"] = user
        if contact:
            filter_params["contact"] = contact
        if identity:
            filter_params["identity"] = identity

        otp_queryset = OTPService().filter(**filter_params)
        otp = otp_queryset.order_by("-date_created").first()
        if not otp:
            raise ValueError("No valid OTP found.")

        if otp.retry_count >= settings.OTP_MAX_RETRIES:
            raise ValueError("Too many incorrect attempts. Please request a new OTP.")

        if self.hash_code(code) != otp.code:
            otp.retry_count += 1
            otp.save()
            raise ValueError("Incorrect OTP.")

        otp.is_used = True

        if otp.identity:
            otp.identity.status = Identity.Status.ACTIVE
            otp.identity.save()

        otp.save()

        return otp
