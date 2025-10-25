from django.contrib import admin

from api.models import ApiClientKey, ApiClient, SystemKey, RateLimitRule, RateLimitAttempt, RateLimitBlock


class ApiClientKeyInline(admin.TabularInline):
    model = ApiClientKey
    extra = 0
    readonly_fields = ('fingerprint', 'date_created', 'date_modified')
    fields = ('public_key', 'fingerprint', 'is_active', 'expires_at', 'date_created', 'date_modified')


@admin.register(ApiClient)
class ApiClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'api_key', 'is_active', 'date_created', 'date_modified')
    search_fields = ('name', 'api_key')
    list_filter = ('is_active',)
    readonly_fields = ('api_key', 'date_created', 'date_modified')
    inlines = [ApiClientKeyInline]

    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'is_active', 'date_created', 'date_modified')
        }),
        ('API Settings', {
            'fields': ('api_key', 'allowed_ips', 'meta')
        }),
    )


@admin.register(SystemKey)
class SystemKeyAdmin(admin.ModelAdmin):
    list_display = ('name', 'fingerprint', 'is_active', 'expires_at', 'date_created', 'date_modified')
    search_fields = ('name', 'fingerprint')
    list_filter = ('is_active',)
    readonly_fields = ('fingerprint', 'date_created', 'date_modified')

    fieldsets = (
        ('Key Info', {
            'fields': ('name', 'public_key', 'private_key', 'fingerprint', 'date_created', 'date_modified')
        }),
        ('Status', {
            'fields': ('is_active', 'expires_at')
        }),
    )


@admin.register(RateLimitRule)
class RateLimitRuleAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'scope', 'limit', 'period_count', 'period',
        'is_active', 'priority', 'block_duration_minutes', 'date_created'
    )
    list_filter = ('scope', 'period', 'is_active', 'date_created')
    search_fields = ('name', 'endpoint_pattern', 'http_methods')
    readonly_fields = ('date_created', 'date_modified')

    fieldsets = (
        ('General', {
            'fields': ('name', 'scope', 'is_active', 'priority')
        }),
        ('Limits', {
            'fields': ('limit', 'period_count', 'period', 'block_duration_minutes')
        }),
        ('Targeting', {
            'fields': ('endpoint_pattern', 'http_methods')
        }),
        ('Timestamps', {
            'fields': ('date_created', 'date_modified')
        }),
    )

    ordering = ('-priority', 'name')


@admin.register(RateLimitAttempt)
class RateLimitAttemptAdmin(admin.ModelAdmin):
    list_display = ('rule', 'key', 'endpoint', 'method', 'count', 'window_start', 'last_attempt')
    list_filter = ('method', 'window_start')
    search_fields = ('key', 'endpoint', 'rule__name')
    readonly_fields = ('date_created', 'date_modified', 'last_attempt')

    fieldsets = (
        ('Rule & Target', {
            'fields': ('rule', 'key', 'endpoint', 'method')
        }),
        ('Attempt Info', {
            'fields': ('count', 'window_start', 'last_attempt')
        }),
        ('Timestamps', {
            'fields': ('date_created', 'date_modified')
        }),
    )

    ordering = ('-last_attempt',)


@admin.register(RateLimitBlock)
class RateLimitBlockAdmin(admin.ModelAdmin):
    list_display = ('rule', 'key', 'blocked_until', 'date_created')
    list_filter = ('blocked_until', 'date_created')
    search_fields = ('key', 'rule__name')
    readonly_fields = ('date_created', 'date_modified')

    fieldsets = (
        ('Rule & Target', {
            'fields': ('rule', 'key')
        }),
        ('Blocking', {
            'fields': ('blocked_until',)
        }),
        ('Timestamps', {
            'fields': ('date_created', 'date_modified')
        }),
    )

    ordering = ('-date_modified',)

