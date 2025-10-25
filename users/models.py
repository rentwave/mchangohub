import logging
import random

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from base.models import BaseModel, GenericBaseModel
from users.manager import CustomUserManager

logger = logging.getLogger(__name__)


class Role(GenericBaseModel):
    is_active = models.BooleanField(default=True)
    auto_generate_password = models.BooleanField(default=False)

    class Meta:
        ordering = ('name', '-date_created',)
        indexes = [
            models.Index(fields=['name', 'is_active']),
        ]

    def __str__(self):
        return self.name


class Permission(GenericBaseModel):
    is_active  = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('-date_created',)
        indexes = [
            models.Index(fields=['name', 'is_active']),
        ]


class RolePermission(BaseModel):
    role = models.ForeignKey('users.Role', null=True, blank=True, on_delete=models.CASCADE)
    permission = models.ForeignKey('users.Permission', null=True, blank=True, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.role.name} - {self.permission.name}"

    class Meta:
        ordering = ('-date_created',)
        unique_together = ('role', 'permission')
        indexes = [
            models.Index(fields=['role', 'permission', 'is_active']),
        ]


class ExtendedPermission(BaseModel):
    user = models.ForeignKey('users.User', null=True, blank=True, on_delete=models.CASCADE)
    permission = models.ForeignKey('users.Permission', null=True, blank=True, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user.username} - {self.permission.name}"

    class Meta:
        ordering = ('-date_created',)
        unique_together = ('user', 'permission')
        indexes = [
            models.Index(fields=['user', 'permission', 'is_active']),
        ]


class User(BaseModel, AbstractUser):
    class Gender(models.TextChoices):
        MALE = "MALE", _("Male")
        FEMALE = "FEMALE", _("Female")
        OTHER = "OTHER", _("Other")

    id_number = models.CharField(max_length=20, null=True, blank=True)
    other_name = models.CharField(max_length=100, null=True, blank=True)
    phone_number = models.CharField(max_length=20)
    other_phone_number = models.CharField(max_length=20, blank=True, null=True)
    gender = models.CharField(max_length=100, choices=Gender.choices, default=Gender.OTHER)
    dob = models.DateTimeField(null=True, blank=True)
    role = models.ForeignKey('users.Role', on_delete=models.CASCADE)
    is_verified = models.BooleanField(default=True)
    last_activity = models.DateTimeField(null=True, blank=True, editable=False)

    manager = CustomUserManager()

    def __str__(self):
        return self.username

    class Meta:
        ordering = ('-date_created',)
        indexes = [
            models.Index(fields=['username', 'is_active']),
            models.Index(fields=['id_number', 'is_active']),
            models.Index(fields=['phone_number', 'is_active']),
            models.Index(fields=['email', 'is_active']),
        ]

    def update_last_activity(self):
        self.last_activity = timezone.now()
        self.save()

    @property
    def full_name(self):
        parts = [self.first_name, self.other_name, self.last_name]
        return " ".join(filter(None, parts))

    def generate_username(self, name: str) -> str:
        name = "user" if not name else name
        username = "%s%s" % (name.lower(), random.randint(10, 999999))
        if User.objects.filter(username=username, is_active=True).exists():
            return self.generate_username(name)
        return username

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.generate_username(self.last_name or self.first_name or "user")
        if not self.role:
            raise ValueError("User's role must be provided")
        super().save(*args, **kwargs)

    @property
    def permissions(self):
        try:
            if self.is_superuser:
                # Return all permissions
                return list(
                    Permission.objects.filter(is_active=True).values_list("name", flat=True)
                )

            # Role-based permissions
            role_permissions = RolePermission.objects.filter(
                role=self.role,
                permission__is_active=True,
                is_active=True
            ).values_list("permission__name", flat=True)

            # Extended (user-specific) permissions
            extended_permissions = ExtendedPermission.objects.filter(
                user=self,
                permission__is_active=True,
                is_active=True
            ).values_list("permission__name", flat=True)

            # Combine both, remove duplicates
            permissions = list(set(role_permissions).union(extended_permissions))

            return permissions

        except Exception as e:
            logger.exception("User model - get_permissions exception: %s" % e)
            return []

    def has_permission(self, permission_name):
        return permission_name in self.permissions


class Device(BaseModel):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)
    token = models.CharField(max_length=255)
    last_activity = models.DateTimeField(null=True, blank=True, editable=False)
    is_active = models.BooleanField(default=True)

    SYNC_MODEL = False

    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"{self.user.username} ({status})"

    class Meta(object):
        ordering = ('-date_created',)
        constraints = [
            models.UniqueConstraint(fields=['user', 'token'], name='unique_user_token')
        ]
        indexes = [
            models.Index(fields=['token']),
        ]