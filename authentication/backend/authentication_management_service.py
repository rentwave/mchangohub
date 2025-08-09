from typing import Optional

from django.db.models import Q
from django.utils import timezone

from authentication.backend.services import IdentityService
from authentication.models import Identity
from otps.backend.otp_management_service import OTPManagementService
from otps.models import OTP
from users.backend.device_management_service import DeviceManagementService
from users.backend.services import UserService


class AuthenticationManagementService:
    @staticmethod
    def login(credential: str, password: str, source_ip: str, device_token: Optional[str]) -> Identity:
        """
        Authenticate a user and issue an identity token.

        :param credential: The user's login credential (username, email, or phone number).
        :type credential: str
        :param password: The user's password.
        :type password: str
        :param source_ip: The IP address from which the login attempt is made.
        :type source_ip: str
        :param device_token: Optional device token for push notifications or device tracking.
        :type device_token: Optional[str]
        :return: The active or newly created Identity object for the authenticated user.
        :rtype: Identity
        :raises Exception: If credentials are invalid.
        """
        filters = Q()
        for field in ["username", "email", "phone_number"]:
            filters |= Q(**{field.lower(): credential})

        user = UserService().filter(filters, is_active=True).first()
        if not user or not user.check_password(password):
            raise Exception("Invalid credentials")

        device = DeviceManagementService().create_device(
            user_id=user.id,
            device_token=device_token
        ) if device_token else None

        identity = IdentityService().filter(
            user=user,
            device=device,
            expires_at__gte=timezone.now(),
            status=Identity.Status.ACTIVE
        ).order_by('-date_created').first()

        if identity is None:
            status = Identity.Status.ACTIVE if user.is_verified else Identity.Status.ACTIVATION_PENDING
            identity = IdentityService().create(
                user=user,
                device=device,
                status = status,
            )
            if status == Identity.Status.ACTIVATION_PENDING:
                OTPManagementService().send_otp(
                    purpose=OTP.PurposeTypes.TWO_FACTOR_AUTHENTICATION,
                    token=identity.token
                )

        IdentityService().filter(
            user=user,
            status=Identity.Status.ACTIVE
        ).exclude(id=identity.id).update(status=Identity.Status.EXPIRED)

        identity.source_ip = source_ip
        identity.extend()

        user.update_last_activity()

        return identity

    @staticmethod
    def logout(user_id: str) -> None:
        """
        Log out a user by expiring all active identities.

        :param user_id: The ID of the user to log out.
        :type user_id: str
        :return: None
        :rtype: None
        :raises ValueError: If the user is not found or inactive.
        """
        user = UserService().get(id=user_id, is_active=True)
        if not user:
            raise ValueError("User not found")

        IdentityService().filter(
            user=user, status=Identity.Status.ACTIVE
        ).update(status=Identity.Status.EXPIRED)

        return

