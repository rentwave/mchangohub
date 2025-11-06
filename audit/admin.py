from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.utils.html import format_html
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from audit.models import RequestLog, AuditLog, AuditConfiguration


class RequestPathCategoryFilter(SimpleListFilter):
    title = "Request Path Category"
    parameter_name = "path_category"

    def lookups(self, request, model_admin):
        return [
            ("health", "Health Checks (/health)"),
            ("api", "API Calls (/api)"),
            ("admin", "Admin (/console)"),
            ("favicon", "Favicon (/favicon)"),
            ("other", "Other"),
        ]

    def queryset(self, request, queryset):
        value = self.value()
        if value == "health":
            return queryset.filter(request_path__startswith="/health")
        elif value == "api":
            return queryset.filter(request_path__startswith="/api")
        elif value == "admin":
            return queryset.filter(request_path__startswith="/console")
        elif value == "favicon":
            return queryset.filter(request_path__startswith="/favicon")
        elif value == "other":
            return queryset.exclude(
                request_path__startswith="/health"
            ).exclude(
                request_path__startswith="/api"
            ).exclude(
                request_path__startswith="/console"
            ).exclude(
                request_path__startswith="/favicon"
            )
        return queryset


@admin.register(RequestLog)
class RequestLogAdmin(admin.ModelAdmin):
    list_display = (
        'request_id', 'api_client', 'user', 'activity_name', 'request_method',
        'colored_status', 'request_path', 'started_at', 'time_taken', 'related_audits_link'
    )
    list_filter = (
        RequestPathCategoryFilter, 'api_client', 'is_authenticated', 'request_method',
        'is_secure', 'activity_name', 'response_status', 'started_at'
    )
    search_fields = (
        'request_id', 'api_client__name', 'user__username', 'token', 'ip_address', 'session_key',
        'request_path', 'activity_name', 'view_name', 'exception_type'
    )
    ordering = ('-started_at',)
    readonly_fields = (
        'request_id', 'started_at', 'ended_at', 'time_taken', 'response_status',
        'response_data', 'id', 'date_created', 'date_modified', 'synced'
    )

    fieldsets = (
        ('Request Info', {
            'fields': (
                'request_id', 'request_method', 'request_path', 'request_data', 'is_secure',
                'user_agent', 'related_audits_link'
            )
        }),
        ('API Client, User & Session', {
            'fields': ('api_client', 'user', 'token', 'is_authenticated', 'ip_address', 'session_key')
        }),
        ('View & Activity', {
            'fields': ('view_name', 'view_args', 'view_kwargs', 'activity_name')
        }),
        ('Timing', {
            'fields': ('started_at', 'ended_at', 'time_taken')
        }),
        ('Response', {
            'fields': ('response_status', 'response_data')
        }),
        ('Exceptions', {
            'fields': ('exception_type', 'exception_message')
        }),
        ('Audit', {
            'fields': ('id', 'date_created', 'date_modified', 'synced')
        }),
    )

    def colored_status(self, obj):
        if obj.response_status is None:
            return "-"
        code = obj.response_status
        if 200 <= code < 300:
            color = "green"
        elif 300 <= code < 400:
            color = "goldenrod"
        elif 400 <= code < 500:
            color = "darkorange"
        else:
            color = "red"
        return format_html('<b style="color:{};">{}</b>', color, code)

    colored_status.short_description = "Status"

    def related_audits_link(self, obj):
        count = AuditLog.objects.filter(request_id=obj.request_id).count()
        if count:
            url = (
                reverse("admin:audit_auditlog_changelist")
                + f"?request_id={obj.request_id}"
            )
            return format_html('<a href="{}" target="_blank">{} related logs</a>', url, count)
        return "—"

    related_audits_link.short_description = "Audit Logs"

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        'date_created', 'summary', 'colored_severity', 'user', 'content_type',
        'object_id', 'view_object_link', 'view_request_link'
    )
    list_filter = ('event_type', 'severity', 'date_created', 'content_type')
    search_fields = ('object_repr', 'object_id', 'user__username', 'request_id')
    readonly_fields = (
        'id', 'date_created', 'date_modified', 'synced', 'request_id',
        'user', 'ip_address', 'user_agent', 'request_method', 'request_path',
        'activity_name', 'content_type', 'object_id', 'object_repr'
    )

    fieldsets = (
        ('Request Information', {
            'fields': (
                'request_id', 'view_request_link', 'user', 'ip_address', 'user_agent',
                'request_method', 'request_path', 'activity_name'
            )
        }),
        ('Event Information', {
            'fields': ('event_type', 'severity')
        }),
        ('Object Information', {
            'fields': ('content_type', 'object_id', 'object_repr', 'view_object_link')
        }),
        ('Change Information', {
            'fields': ('changes',)
        }),
        ('Additional Context', {
            'fields': ('metadata',)
        }),
        ('Audit', {
            'fields': ('id', 'date_created', 'date_modified', 'synced')
        }),
    )

    def summary(self, obj):
        model_label = obj.content_type.model if obj.content_type else "Unknown Model"
        if obj.event_type == 'create':
            action = "Created"
        elif obj.event_type == 'update':
            action = "Updated"
        elif obj.event_type == 'delete':
            action = "Deleted"
        elif obj.event_type == 'view':
            action = "Viewed"
        else:
            action = obj.event_type.title()
        return f"{action} {model_label.capitalize()} ({obj.object_repr or obj.object_id})"
    summary.short_description = _("Summary")

    def colored_severity(self, obj):
        colors = {
            'low': 'green',
            'medium': 'orange',
            'high': 'red',
            'critical': 'darkred'
        }
        color = colors.get(obj.severity, 'gray')
        return format_html('<b><span style="color:{};">{}</span></b>', color, obj.severity.title())
    colored_severity.short_description = _("Severity")

    def view_request_link(self, obj):
        if not obj.request_id:
            return "-"
        try:
            req = RequestLog.objects.get(request_id=obj.request_id)
            url = reverse('admin:audit_requestlog_change', args=[req.pk])
            return format_html('<a href="{}" target="_blank">View Request</a>', url)
        except RequestLog.DoesNotExist:
            return "-"
    view_request_link.short_description = _("Request Log")

    def view_object_link(self, obj):
        if not obj.content_type or not obj.object_id:
            return "-"
        try:
            model_class = obj.content_type.model_class()
            if not model_class:
                return "-"
            instance = model_class.objects.filter(pk=obj.object_id).first()
            if instance:
                url = reverse(
                    f"admin:{obj.content_type.app_label}_{obj.content_type.model}_change",
                    args=[obj.object_id]
                )
                return format_html('<a href="{}" target="_blank">View Object</a>', url)
            else:
                return format_html('<span style="color: #999;">Deleted</span>')
        except Exception:
            return "-"
    view_object_link.short_description = _("Object")

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(AuditConfiguration)
class AuditConfigurationAdmin(admin.ModelAdmin):
    list_display = ('app_label', 'model_name', 'is_enabled', 'track_create', 'track_update', 'track_delete')
    list_filter = ('is_enabled', 'track_create', 'track_update', 'track_delete')
    search_fields = ('app_label', 'model_name')
    readonly_fields = ('id', 'date_created', 'date_modified', 'synced')
    fieldsets = (
        ('Model Information', {
            'fields': ('app_label', 'model_name')
        }),
        ('Tracking Options', {
            'fields': ('is_enabled', 'track_create', 'track_update', 'track_delete', 'excluded_fields')
        }),
        ('Retention', {
            'fields': ('retention_days',)
        }),
        ('Audit', {
            'fields': ('id', 'date_created', 'date_modified', 'synced')
        }),
    )
