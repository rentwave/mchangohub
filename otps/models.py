from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from base.models import BaseModel


class OTP(BaseModel):
    class PurposeTypes(models.TextChoices):
        PHONE_VERIFICATION = "PHONE_VERIFICATION", _("Phone Verification")
        EMAIL_VERIFICATION = "EMAIL_VERIFICATION", _("Email Verification")
        TWO_FACTOR_AUTHENTICATION = "2FA", _("Two-Factor Authentication")
        PASSWORD_RESET = "PASSWORD_RESET", _("Password Reset")

    class DeliveryMethods(models.TextChoices):
        SMS = "SMS", _("SMS")
        EMAIL = "EMAIL", _("Email")

    user = models.ForeignKey('users.User', null=True, blank=True, on_delete=models.CASCADE)
    purpose = models.CharField(max_length=32, choices=PurposeTypes.choices)
    identity = models.ForeignKey(
        'authentication.Identity', null=True, blank=True, on_delete=models.CASCADE, related_name="otps")
    code = models.CharField(max_length=255)  # hashed
    delivery_method = models.CharField(max_length=10, choices=DeliveryMethods.choices)
    contact = models.CharField(max_length=255)  # phone or email
    expires_at = models.DateTimeField(null=True, blank=True)
    is_used = models.BooleanField(default=False)
    retry_count = models.IntegerField(default=0)

    class Meta:
        ordering = ('-date_created',)

    def is_expired(self):
        return timezone.now() > self.expires_at
