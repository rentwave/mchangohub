import secrets
from datetime import timedelta
from django.db import models
from base.models import BaseModel


class ApiClient(BaseModel):
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Name of the external system or partner."
    )
    api_key = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        help_text="Unique API key identifying this client."
    )
    allowed_ips = models.TextField(
        blank=True,
        help_text="Comma-separated list of allowed IPs for request validation."
    )
    signature_secret = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Shared secret for HMAC signature validation of callbacks."
    )
    signature_header_key = models.CharField(
        max_length=50,
        default="x-signature",
        help_text="Header name containing the callback signature."
    )
    signature_algorithm = models.CharField(
        max_length=20,
        choices=[("HMAC-SHA256", "HMAC-SHA256"), ("RSA-SHA256", "RSA-SHA256")],
        default="HMAC-SHA256",
        help_text="Algorithm used to verify callback signatures."
    )
    require_signature_verification = models.BooleanField(
        default=False,
        help_text="If True, incoming requests must include a valid cryptographic signature."
    )
    meta = models.JSONField(
        blank=True,
        null=True,
        help_text="Optional metadata about the client (contact info, environment, etc.)."
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "API Client"
        verbose_name_plural = "API Clients"
        ordering = ["name"]

    def save(self, *args, **kwargs):
        import secrets
        if not self.api_key:
            self.api_key = secrets.token_hex(32)
        super().save(*args, **kwargs)

    def get_active_public_key(self):
        return self.keys.filter(is_active=True).order_by("-date_created").first()

    def __str__(self):
        return f"{self.name} ({'Active' if self.is_active else 'Inactive'})"


class ApiClientKey(BaseModel):
    client = models.ForeignKey(
        ApiClient,
        on_delete=models.CASCADE,
        related_name="keys",
        help_text="Owning API client for this key."
    )
    public_key = models.TextField(
        help_text="The client's public key in PEM format."
    )
    fingerprint = models.CharField(
        max_length=64,
        db_index=True,
        help_text="SHA-256 fingerprint of the public key for quick lookup."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Indicates if this key is currently active."
    )
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "API Client Key"
        verbose_name_plural = "API Client Keys"
        unique_together = ["client", "fingerprint"]
        ordering = ["-date_created"]

    def __str__(self):
        return f"{self.client.name} [{self.fingerprint[:12]}...]"

    def deactivate_others(self):
        self.client.keys.exclude(id=self.id).update(is_active=False)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_active:
            self.deactivate_others()


class SystemKey(BaseModel):
    name = models.CharField(max_length=100, unique=True, default="default")
    public_key = models.TextField(help_text="Public key (shared with partners).")
    private_key = models.TextField(help_text="Private key")
    fingerprint = models.CharField(
        max_length=64,
        unique=True,
        help_text="SHA-256 fingerprint of the public key."
    )
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "System Key"
        verbose_name_plural = "System Keys"
        ordering = ["-date_created"]

    def __str__(self):
        return f"{self.name} [{self.fingerprint[:12]}...]"


class APICallback(BaseModel):
    client = models.ForeignKey(
        ApiClient,
        on_delete=models.CASCADE,
        related_name="callbacks",
        help_text="API client associated with this callback."
    )
    path = models.CharField(
        max_length=255,
        unique=True,
        help_text="URL path pattern or endpoint for the callback."
    )
    require_authentication = models.BooleanField(
        default=False,
        help_text="If True, the callback requires API key authentication."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Indicates whether this callback is active."
    )

    class Meta:
        verbose_name = "API Callback"
        verbose_name_plural = "API Callbacks"
        ordering = ["client__name", "path"]
        unique_together = ["client", "path"]

    def __str__(self):
        return f"{self.client.name} → {self.path} ({'Active' if self.is_active else 'Inactive'})"


class RateLimitRule(BaseModel):
    SCOPE_CHOICES = [
        ('global', 'Global'),
        ('api_client', 'API Client'),
        ('user', 'Per User'),
        ('ip', 'Per IP'),
        ('endpoint', 'Per Endpoint'),
        ('api_client_endpoint', 'Per API Client + Endpoint'),
        ('user_endpoint', 'Per User + Endpoint'),
        ('ip_endpoint', 'Per IP + Endpoint'),
    ]

    PERIOD_CHOICES = [
        ('second', 'Second'),
        ('minute', 'Minute'),
        ('hour', 'Hour'),
        ('day', 'Day'),
        ('week', 'Week'),
        ('month', 'Month'),
    ]

    name = models.CharField(max_length=100, unique=True)
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES)
    limit = models.PositiveIntegerField(help_text="Number of requests allowed")
    period = models.CharField(max_length=10, choices=PERIOD_CHOICES)
    period_count = models.PositiveIntegerField(default=1, help_text="Number of periods (e.g., 2 for '2 hours')")
    endpoint_pattern = models.CharField(max_length=200, blank=True, help_text="Regex pattern for URL matching")
    http_methods = models.CharField(max_length=50, blank=True, help_text="Comma-separated HTTP methods (GET,POST,etc)")
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=0, help_text="Higher priority rules are checked first")
    block_duration_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Block duration after limit exceeded (0 = no blocking)"
    )

    class Meta:
        ordering = ['name', '-priority']

    def __str__(self):
        return f"{self.name}: {self.limit}/{self.period_count} {self.period}(s) - {self.scope}"

    def get_period_timedelta(self):
        period_map = {
            'second': timedelta(seconds=self.period_count),
            'minute': timedelta(minutes=self.period_count),
            'hour': timedelta(hours=self.period_count),
            'day': timedelta(days=self.period_count),
            'week': timedelta(weeks=self.period_count),
            'month': timedelta(days=self.period_count * 30),
        }
        return period_map.get(self.period, timedelta(minutes=self.period_count))


class RateLimitAttempt(BaseModel):
    rule = models.ForeignKey(RateLimitRule, on_delete=models.CASCADE)
    key = models.CharField(max_length=255, db_index=True)
    endpoint = models.CharField(max_length=200, blank=True)
    method = models.CharField(max_length=10)
    count = models.PositiveIntegerField(default=1)
    window_start = models.DateTimeField(db_index=True)
    last_attempt = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_attempt']
        unique_together = ['rule', 'key', 'endpoint', 'window_start']
        indexes = [
            models.Index(fields=['rule', 'key', 'window_start']),
            models.Index(fields=['window_start']),
        ]


class RateLimitBlock(BaseModel):
    rule = models.ForeignKey(RateLimitRule, on_delete=models.CASCADE)
    key = models.CharField(max_length=255, db_index=True)
    blocked_until = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ['-date_modified']
        unique_together = ['rule', 'key']