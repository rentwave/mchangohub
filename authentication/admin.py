from django.contrib import admin
from .models import Identity, LoginLog


@admin.register(Identity)
class IdentityAdmin(admin.ModelAdmin):
    list_display = ('user', 'device', 'status', 'token', 'expires_at', 'source_ip', 'date_created')
    list_filter = ('status', 'expires_at', 'date_created')
    search_fields = (
        'user__id', 'user__username', 'user__first_name', 'user__last_name',
        'user__phone_number', 'device__token', 'token', 'source_ip'
    )
    readonly_fields = ('token', 'date_created', 'date_modified')

    fieldsets = (
        ('User & Status', {
            'fields': ('user', 'device', 'status')
        }),
        ('Token Info', {
            'fields': ('token', 'expires_at', 'source_ip'),
        }),
        ('Timestamps', {
            'fields': ('date_created', 'date_modified')
        }),
    )

    ordering = ('-date_created',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LoginLog)
class LoginLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'date_created')
    search_fields = ('user__username',)
    ordering = ('-date_created',)

    fieldsets = (
        ('User Info', {
            'fields': ('user',)
        }),
        ('Timestamps', {
            'fields': ('date_created', 'date_modified')
        }),
    )

    readonly_fields = ('date_created', 'date_modified')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
