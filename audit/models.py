from django.db import models

from base.models import BaseModel


class AuditLog(BaseModel):
    action = models.CharField(max_length=100, null=True, blank=True)
    user = models.ForeignKey('users.User', null=True, blank=True, on_delete=models.SET_NULL)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    request_path = models.CharField(max_length=1000, null=True, blank=True)
    request_method = models.CharField(max_length=10, null=True, blank=True)
    request_data = models.JSONField(default=dict, null=True, blank=True)
    response_data = models.JSONField(default=dict, null=True, blank=True)
    response_status_code = models.IntegerField(null=True, blank=True)
    successful = models.BooleanField(default=False)

    class Meta:
        ordering = ('-date_created',)
        indexes = [
            models.Index(fields=['action']),
            models.Index(fields=['user']),
            models.Index(fields=['successful']),
        ]

    def __str__(self):
        return f"{self.action or 'unknown'} by {self.user or 'anonymous'}"


