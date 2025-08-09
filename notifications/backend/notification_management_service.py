import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional

import requests
from django.conf import settings

from mchangohub.celery import app
from notifications.backend.services import NotificationService
from notifications.models import Notification
from users.backend.services import DeviceService
from users.models import User

logger = logging.getLogger(__name__)


class NotificationManagementService:
    """
    Manages creation, deduplication, and dispatch of notifications for a given user.
    """

    def __init__(self, user: Optional[User]):
        """
        Initialize the service with an optional target user.

        :param user: The user who will receive notifications, or None when sending to arbitrary recipients.
        :type user: Optional[User]
        """
        self.user = user

    def _generate_unique_key(self, notification_key: str, frequency: str) -> str:
        """
        Generate a SHA256 unique key for deduplication based on user, notification key, and frequency.

        :param notification_key: A unique string identifying the notification type.
        :type notification_key: str
        :param frequency: Notification frequency ("monthly", "weekly", "daily", or "once").
        :type frequency: str
        :return: A SHA256 hash that represents the unique key for this notification.
        :rtype: str
        """
        today = datetime.now()
        if frequency == 'monthly':
            key_string = f"{self.user.id}_{notification_key}_{today.year}_{today.month}"
        elif frequency == 'weekly':
            year, week_num, _ = today.isocalendar()
            key_string = f"{self.user.id}_{notification_key}_{year}_{week_num}"
        elif frequency == 'daily':
            key_string = f"{self.user.id}_{notification_key}_{today.date()}"
        else:
            key_string = f"{self.user.id}_{notification_key}"
        return hashlib.sha256(key_string.encode()).hexdigest()

    @staticmethod
    def _get_deduplication_window(frequency: str) -> Optional[timedelta]:
        """
        Get the time window used to check for duplicate notifications.

        :param frequency: Notification frequency ("monthly", "weekly", "daily", or "once").
        :type frequency: str
        :return: Timedelta for the deduplication period, or None if once-only.
        :rtype: Optional[timedelta]
        """
        if frequency == 'monthly':
            return timedelta(days=31)
        elif frequency == 'weekly':
            return timedelta(days=7)
        elif frequency == 'daily':
            return timedelta(hours=24)
        else:
            return None

    def _is_duplicate(self, unique_key: str, frequency: str) -> bool:
        """
        Check if a notification with the same unique key exists within the deduplication window.

        :param unique_key: The hashed unique key for the notification.
        :type unique_key: str
        :param frequency: Notification frequency.
        :type frequency: str
        :return: True if a duplicate exists, False otherwise.
        :rtype: bool
        """
        window = self._get_deduplication_window(frequency)
        if window is None:
            return NotificationService().filter(
                user=self.user,
                unique_key=unique_key
            ).exists()
        return NotificationService().filter(
            user=self.user,
            unique_key=unique_key,
            date_created__gte=datetime.now() - window
        ).exists()

    def send_notification(
        self,
        context: dict,
        delivery_method: str = Notification.DeliveryMethods.PUSH,
        template: str = "push_default",
        notification_key: Optional[str] = None,
        frequency: str = Notification.NotificationFrequency.ONCE
    ) -> Optional[Notification]:
        """
        Create, validate for duplicates, store, and send or queue a notification.

        :param context: Notification context variables.
        :type context: dict
        :param delivery_method: Notification delivery method (e.g., PUSH, SMS, EMAIL).
        :type delivery_method: str
        :param template: Notification template identifier.
        :type template: str
        :param notification_key: Optional deduplication key for the notification type.
        :type notification_key: Optional[str]
        :param frequency: Frequency for deduplication.
        :type frequency: str
        :return: The created Notification object, or None if duplicate.
        :rtype: Optional[Notification]
        :raises ValueError: If delivery method or frequency is invalid.
        :raises Exception: If notification creation fails.
        """
        delivery_method = delivery_method.upper()
        if delivery_method not in Notification.DeliveryMethods.values:
            raise ValueError("Invalid delivery method")

        frequency = frequency.upper()
        if frequency not in Notification.NotificationFrequency.values:
            raise ValueError("Invalid notification frequency")

        unique_key = None
        if notification_key:
            unique_key = self._generate_unique_key(notification_key, frequency)
            if self._is_duplicate(unique_key=unique_key, frequency=frequency):
                return None

        notification = NotificationService().create(
            user=self.user,
            delivery_method=delivery_method,
            template=template,
            context=context,
            unique_key=unique_key,
            frequency=frequency,
        )

        if notification is None:
            raise Exception("Error creating notification")

        recipient = None
        if delivery_method == Notification.DeliveryMethods.SMS:
            recipient = notification.user.phone_number
        elif delivery_method == Notification.DeliveryMethods.EMAIL:
            recipient = notification.user.email
        else:
            device = DeviceService().filter(user=notification.user, is_active=True).first()
            if device:
                recipient = device.token

        if not recipient:
            logger.error("NotificationManagementService - save_notification exception: No valid recipient found")
            notification.status = Notification.Status.FAILED
            notification.save()
            return notification

        notification_data = {
            "unique_identifier": str(notification.id),
            "system": "mchangohub",
            "recipients": [recipient],
            "notification_type": notification.delivery_method,
            "template": template,
            "context": context,
        }

        self._send_or_queue(notification_data)

        notification.status = Notification.Status.QUEUED
        notification.save()

        return notification

    def send_to_recipients(
            self,
            recipients: list[str],
            context: dict,
            delivery_method: str = Notification.DeliveryMethods.SMS,
            template: str = "sms_default"
    ) -> None:
        """
        Send a notification directly to a list of recipients without associating with a User.

        :param recipients: List of recipient identifiers (phone numbers, emails, or device tokens).
        :type recipients: list[str]
        :param context: Variables to populate the notification template.
        :type context: dict
        :param delivery_method: Delivery method (e.g., PUSH, SMS, EMAIL).
        :type delivery_method: str
        :param template: Identifier for the notification template to use.
        :type template: str
        :raises ValueError: If delivery method is invalid or the recipients' list is empty.
        """
        delivery_method = delivery_method.upper()
        if delivery_method not in Notification.DeliveryMethods.values:
            raise ValueError("Invalid delivery method")

        if not recipients:
            raise ValueError("Recipients list cannot be empty")

        notification_data = {
            "unique_identifier": "",
            "system": "mchangohub",
            "recipients": recipients,
            "notification_type": delivery_method,
            "template": template,
            "context": context,
        }

        self._send_or_queue(notification_data)

    def _send_or_queue(self, notification_data: dict) -> None:
        """
        Send or queue the notification payload based on the system settings.

        :param notification_data: The notification payload dictionary to send or queue.
        :type notification_data: dict
        """
        if settings.QUEUE_NOTIFICATIONS:
            self._queue_notification(notification_data)
        else:
            self._make_request(notification_data)

    @staticmethod
    def _queue_notification(data: dict):
        """
        Queue notification for asynchronous processing.

        :param data: Notification payload to be sent to the task queue.
        :type data: dict
        """
        app.send_task(
            "notify.send_notification",
            args=(data,),
            queue="notification_queue"
        )

    @staticmethod
    def _make_request(notification_data: dict):
        """
        Send notification directly to the external notification service.

        :param notification_data: Payload to be sent to the external service.
        :type notification_data: dict
        :raises requests.HTTPError: If the request fails.
        """
        response = requests.post(
            f"{settings.NOTIFY_BASE_URL}/core/send-notification/",
            json=notification_data
        )
        response.raise_for_status()

