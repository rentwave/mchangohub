from users.models import Role, Permission, RolePermission, ExtendedPermission, User, Device
from utils.service_base import ServiceBase


class RoleService(ServiceBase):
    manager = Role.objects


class PermissionService(ServiceBase):
    manager = Permission.objects


class RolePermissionService(ServiceBase):
    manager = RolePermission.objects


class ExtendedPermissionService(ServiceBase):
    manager = ExtendedPermission.objects


class UserService(ServiceBase):
    manager = User.objects


class DeviceService(ServiceBase):
    manager = Device.objects