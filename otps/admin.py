from django.contrib import admin

from otps.models import OTP


@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'purpose', 'delivery_method', 'contact', 'expires_at', 'is_used',
        'retry_count', 'date_created'
    )
    list_filter = ('purpose', 'delivery_method', 'is_used')
    search_fields = (
        'contact', 'user__id', 'user__username', 'user__spin_id', 'user__email',
        'user__phone_number', 'user__other_phone_number', 'user__first_name',
        'user__last_name', 'user__other_name', 'identity__token'
    )
    autocomplete_fields = ('user', 'identity')
    readonly_fields = ('code', 'date_created', 'expires_at')
    ordering = ('-date_created',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return True