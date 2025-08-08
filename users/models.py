import random

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from base.models import BaseModel, GenericBaseModel
from users.manager import CustomUserManager


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


class ExtendedPermissions(BaseModel):
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

    def full_name(self):
        return "%s %s %s" % (self.first_name, self.other_name, self.last_name)

    def generate_username(self, name: str) -> str:
        name = "user" if not name else name
        username = "%s%s" % (name.lower(), random.randint(10, 999999))
        if User.objects.filter(username=username, is_active=True).exists():
            return self.generate_username(name)
        return username

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.generate_username(self.first_name or self.last_name or "user")
        if not self.role:
            raise ValueError("User's role must be provided")
        super().save(*args, **kwargs)