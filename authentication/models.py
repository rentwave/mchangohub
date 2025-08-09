import logging
import base64
import binascii
import os
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from base.models import BaseModel

logger = logging.getLogger(__name__)


class Identity(BaseModel):
    class Status(models.TextChoices):
        ACTIVATION_PENDING = "ACTIVATION_PENDING", _("Activation Pending")
        ACTIVE = "ACTIVE", _("Active")
        EXPIRED = "EXPIRED", _("Expired")

    user = models.ForeignKey('users.User', on_delete=models.CASCADE)
    device = models.ForeignKey('users.Device', null=True, blank=True, on_delete=models.CASCADE)
    token = models.CharField(max_length=200)
    expires_at = models.DateTimeField()
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVATION_PENDING)

    class Meta(object):
        ordering = ('-date_created',)
        verbose_name_plural = 'Identities'
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['token', 'status']),
            models.Index(fields=['user', 'device', 'status']),
        ]

    def _str_(self):
        return f"{self.user.username} - ({self.status})"

    @staticmethod
    def generate_token() -> Optional[str]:
        try:
            data_string = binascii.hexlify(os.urandom(15)).decode()
            timestamp = timezone.now().strftime("%Y%m%d%H%M%S%f")[:-3]
            full_string = f"{data_string}{timestamp}"
            token = base64.b64encode(full_string.encode("utf-8")).decode("utf-8")
            return token
        except Exception as ex:
            logger.exception(f"Identity - generate_token exception: {ex}")
            return None

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = self.generate_token()
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(seconds=settings.TOKEN_VALIDITY_SECONDS)
        super().save(*args, **kwargs)

    def extend(self):
        # noinspection PyBroadException
        try:
            now = timezone.now()
            self.expires_at = now + timedelta(seconds=settings.TOKEN_VALIDITY_SECONDS)
            self.save()
        except Exception:
            pass
        return self


class LoginLog(BaseModel):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)

    class Meta:
        ordering = ('-date_created',)

    def __str__(self):
        return f"{self.user.username} @ {self.date_created}"




