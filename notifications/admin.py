from django.contrib import admin
from .models import Notification

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'delivery_method', 'template', 'frequency', 'status', 'sent_time', 'date_created'
    )
    list_filter = ('delivery_method', 'frequency', 'status', 'date_created')
    search_fields = (
        'user__username', 'user__first_name', 'user__last_name', 'user__other_name',
        'user__id_number', 'user__email', 'user_phone_number', 'template', 'unique_key'
    )
    readonly_fields = ('date_created', 'date_modified', 'sent_time')

    fieldsets = (
        (None, {
            'fields': ('user', 'delivery_method', 'template', 'frequency', 'unique_key')
        }),
        ('Status & Response', {
            'fields': ('status', 'sent_time', 'response_data')
        }),
        ('Additional Info', {
            'fields': ('context',)
        }),
        ('Timestamps', {
            'fields': ('date_created', 'date_modified')
        }),
    )
