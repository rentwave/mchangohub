from django.db import models
from django.utils.translation import gettext_lazy as _

from base.models import BaseModel


class Notification(BaseModel):
    class NotificationFrequency(models.TextChoices):
        ONCE = "ONCE", _("Once")
        DAILY = "DAILY", _("Daily")
        WEEKLY = "WEEKLY", _("Weekly")
        MONTHLY = "MONTHLY", _("Monthly")

    class DeliveryMethods(models.TextChoices):
        SMS = "SMS", _("SMS")
        EMAIL = "EMAIL", _("Email")
        PUSH = "PUSH", _("Push")

    class Status(models.TextChoices):
        PENDING = "PENDING", _("Pending")
        QUEUED = "QUEUED", _("Queued")
        CONFIRMATION_PENDING = "CONFIRMATION_PENDING", _("Confirmation Pending")
        SENT = "SENT", _("Sent")
        FAILED = "FAILED", _("Failed")

    user = models.ForeignKey('users.User', null=True, blank=True, on_delete=models.CASCADE)
    delivery_method = models.CharField(max_length=10, choices=DeliveryMethods.choices, default=DeliveryMethods.PUSH)
    context = models.JSONField(default=dict)
    template = models.CharField(max_length=100)
    frequency = models.CharField(
        max_length=20, choices=NotificationFrequency.choices, default=NotificationFrequency.ONCE)
    unique_key = models.CharField(
        max_length=255, null=True, blank=True, unique=True,
        help_text="Unique key to identify the notification. Generated when saving the notification")
    recipients = models.JSONField(default=list, help_text="List of recipients for the notification.")
    sent_time = models.DateTimeField(blank=True, null=True)
    response_data = models.JSONField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)


    class Meta:
        indexes = [
            models.Index(fields=['user', 'date_created']),
            models.Index(fields=['unique_key'])
        ]
        ordering = ('-date_created',)

    def _str_(self):
        return '%s - %s' % (self.user, self.delivery_method)
