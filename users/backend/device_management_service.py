import logging

from django.utils import timezone

from authentication.backend.services import IdentityService
from authentication.models import Identity
from users.backend.services import UserService, DeviceService
from users.models import Device

logger = logging.getLogger(__name__)


class DeviceManagementService:
    @staticmethod
    def create_device(user_id: str, device_token: str) -> Device:
        """
        Create or update a device for a user.

        :param user_id: ID of the user who is creating or updating the device
        :type user_id: str
        :param device_token: Unique token representing the device
        :type device_token: str
        :return: The created or updated device instance
        :rtype: Device
        :raises Exception: If the user is not found or device creation fails
        """
        # Check if the user exists
        user = UserService().get(id=user_id, is_active=True)
        if not user:
            raise Exception("User not found")

        now = timezone.now()
        device = DeviceService().get(token=device_token)

        if device:
            if device.user != user:
                if device.is_active:
                    previous_user = device.user
                    previous_user.is_verified = False
                    previous_user.save()

                    # Revoke the previous user's identity on this device
                    IdentityService().filter(
                        user=previous_user,
                        device=device,
                        status=Identity.Status.ACTIVE
                    ).update(status=Identity.Status.EXPIRED)

                user.is_verified = False
                user.save()

                device.user = user

            device.is_active = True
            device.last_activity = now
            device.save()

        else:
            # Create a new device
            device = DeviceService().create(
                user=user,
                token=device_token,
                last_activity=now,
                is_active=True
            )
            if device is None:
                raise Exception("Failed to create device")

            user.is_verified = False
            user.save()


        # Revoke other active devices
        DeviceService().filter(
            user=user, is_active=True
        ).exclude(id=device.id).update(is_active=False)

        IdentityService().filter(
            user=user,
            status=Identity.Status.ACTIVE
        ).exclude(device=device).update(status=Identity.Status.EXPIRED)

        return device

    @staticmethod
    def deactivate_device(device_id: str) -> Device:
        """
        Deactivates a device and expires any active identities associated with the device.

        :param device_id: The ID of the device to deactivate.
        :raises Exception: If the device is not found.
        :rtype: Device
        :return: The deactivated Device object.
        """
        # Check if the device exists
        device = DeviceService().get(id=device_id)
        if device is None:
            raise Exception("Device not found")

        if device.is_active:
            # Expire the identities associated with the device
            IdentityService().filter(
                device=device, status=Identity.Status.ACTIVE
            ).update(status=Identity.Status.EXPIRED)

            # Deactivate device
            device.is_active = False
            device.save()

        return device

