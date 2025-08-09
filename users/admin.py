from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _
from users.models import Role, Permission, RolePermission, ExtendedPermission, User, Device

admin.site.unregister(Group)


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'auto_generate_password', 'date_created')
    list_filter = ('is_active',)
    search_fields = ('name',)
    ordering = ('name', '-date_created')


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'date_created')
    list_filter = ('is_active',)
    search_fields = ('name',)
    ordering = ('-date_created',)


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ('role', 'permission', 'is_active', 'date_created')
    list_filter = ('is_active', 'role', 'permission')
    search_fields = ('role__name', 'permission__name')
    ordering = ('-date_created',)


@admin.register(ExtendedPermission)
class ExtendedPermissionsAdmin(admin.ModelAdmin):
    list_display = ('user', 'permission', 'is_active', 'date_created')
    list_filter = ('is_active', 'permission')
    search_fields = ('user__username', 'permission__name')
    ordering = ('-date_created',)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = (
        (None, {'fields': ('username',)}),
        (_('Personal info'), {
            'fields': (
                'id_number', 'first_name', 'last_name', 'other_name', 'email',
                'phone_number', 'other_phone_number', 'gender', 'dob'
            )
        }),
        (_('Role & Permissions'), {
            'fields': ('role', 'is_active', 'is_verified', 'is_staff', 'is_superuser')
        }),
        (_('Important dates'), {
            'fields': (
                'last_login', 'last_activity', 'date_created', 'date_modified'
            )
        }),
        (_('Password'), {'fields': ('password',), 'classes': ('collapse',)}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'username', 'password1', 'password2', 'first_name',
                'last_name', 'other_name', 'email', 'phone_number', 'role'
            ),
        }),
    )

    list_display = (
        'username', 'first_name', 'last_name', 'email', 'phone_number', 'role',
        'is_verified', 'is_superuser', 'is_active', 'date_modified',  'date_created'
    )
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'is_verified', 'role')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'phone_number', 'id_number')
    readonly_fields = ('last_login', 'last_activity', 'date_created', 'date_modified')
    ordering = ('-date_created',)


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('user', 'token', 'is_active', 'last_activity', 'date_created')
    list_filter = ('is_active', 'last_activity', 'date_created')
    search_fields = (
        'token', 'user__username', 'user__id_number', 'user__phone_number', 'user__email',
        'user__first_name', 'user__last_name'
    )
    readonly_fields = ('last_activity', 'date_created', 'date_modified')
    ordering = ('-date_created',)



