from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        'action', 'user', 'ip_address', 'request_data', 'response_data',
        'response_status_code', 'successful', 'date_created',
    )
    list_filter = (
        'successful', 'action', 'response_status_code', 'date_created'
    )
    search_fields = (
        'action', 'user__id', 'user__username', 'user__email', 'user__phone_number',
        'user__other_phone_number', 'user__first_name', 'user__last_name',
        'user__other_name', 'ip_address', 'request_path', 'response_status_code'
    )
    readonly_fields = (
        'action', 'user', 'ip_address', 'request_path', 'request_method',
        'request_data', 'response_data', 'response_status_code',
        'successful', 'date_created', 'date_modified',
    )
    fieldsets = (
        ("Request Info", {
            'fields': (
                'action',
                'user',
                'ip_address',
                'request_path',
                'request_method',
                'request_data',
            )
        }),
        ("Response Info", {
            'fields': (
                'response_data',
                'response_status_code',
                'successful',
            )
        }),
        ("Timestamps", {
            'fields': (
                'date_created',
                'date_modified',
            )
        }),
    )
    ordering = ('-date_created',)
    date_hierarchy = 'date_created'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


