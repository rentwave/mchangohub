from django.contrib import admin
from django.utils.html import format_html
from .models import (
    State, BalanceEntryType, ExecutionProfile, RuleProfile, RuleProfileCommand,
    EntryType, AccountFieldType, PaymentMethod
)


@admin.register(State)
class StateAdmin(admin.ModelAdmin):
    """Admin for State model with color coding"""
    list_display = ['name', 'color_display', 'description',  'date_created']
    list_filter = ['date_created']
    search_fields = ['name', 'description']
    readonly_fields = ['date_created', 'date_modified']

    fieldsets = (
        ('State Information', {
            'fields': ('name', 'description', 'color',)
        }),
        ('Timestamps', {
            'fields': ('date_created', 'date_modified'),
            'classes': ('collapse',)
        }),
    )

    def color_display(self, obj):
        if hasattr(obj, 'color') and obj.color:
            return format_html(
                '<div style="width: 20px; height: 20px; background-color: {}; '
                'border: 1px solid #ccc; border-radius: 3px; display: inline-block; '
                'margin-right: 10px;"></div>{}',
                obj.color, obj.color
            )
        return '-'

    color_display.short_description = "Color"

    def get_state_color(state_name, default_color="#6c757d"):
        """Get color for state, with fallbacks for common state names"""
        color_mapping = {
            'pending': '#dc3545',  # Red
            'partially paid': '#ffc107',  # Yellow/Orange
            'cleared': '#28a745',  # Green
            'cancelled': '#6c757d',  # Gray
            'overdue': '#fd7e14',  # Orange
            'confirmed': '#17a2b8',  # Teal
            'processing': '#007bff',  # Blue
            'on hold': '#6f42c1',  # Purple
        }

        # Try exact match first
        state_key = state_name.lower().strip()
        if state_key in color_mapping:
            return color_mapping[state_key]

        # Try partial matches
        for key, color in color_mapping.items():
            if key in state_key or state_key in key:
                return color

        return default_color


@admin.register(BalanceEntryType)
class BalanceEntryTypeAdmin(admin.ModelAdmin):
    """Manage balance entry types."""
    list_display = ("name", "description", "date_created")
    search_fields = ("name", "description")
    ordering = ("name",)


@admin.register(ExecutionProfile)
class ExecutionProfileAdmin(admin.ModelAdmin):
    """Manage execution profiles."""
    list_display = ("name", "description", "date_created")
    search_fields = ("name", "description")
    ordering = ("name",)


class RuleProfileCommandInline(admin.TabularInline):
    """Inline commands under a RuleProfile."""
    model = RuleProfileCommand
    extra = 0
    readonly_fields = ("name", "order", "state", "date_created")
    can_delete = False
    ordering = ("order",)


@admin.register(RuleProfile)
class RuleProfileAdmin(admin.ModelAdmin):
    """Manage rule profiles."""
    list_display = ("execution_profile_link", "name", "order", "sleep_seconds", "date_created")
    list_filter = ("execution_profile",)
    search_fields = ("name", "execution_profile__name")
    ordering = ("execution_profile__name", "order")
    inlines = [RuleProfileCommandInline]

    def execution_profile_link(self, obj):
        """Clickable ExecutionProfile link."""
        return format_html('<a href="/admin/app_name/executionprofile/{}/change/">{}</a>',
                           obj.execution_profile.id, obj.execution_profile)
    execution_profile_link.short_description = "Execution Profile"


@admin.register(RuleProfileCommand)
class RuleProfileCommandAdmin(admin.ModelAdmin):
    """Manage commands inside rule profiles."""
    list_display = ("name", "rule_profile_link", "state", "order", "date_created")
    list_filter = ("state",)
    search_fields = ("name", "rule_profile__name", "state__name")
    ordering = ("rule_profile__execution_profile__name", "rule_profile__order", "order")

    def rule_profile_link(self, obj):
        """Clickable RuleProfile link."""
        return format_html('<a href="/admin/app_name/ruleprofile/{}/change/">{}</a>',
                           obj.rule_profile.id, obj.rule_profile)
    rule_profile_link.short_description = "Rule Profile"


@admin.register(EntryType)
class EntryTypeAdmin(admin.ModelAdmin):
    """Manage account entry types."""
    list_display = ("name", "description", "date_created")
    search_fields = ("name", "description")
    ordering = ("name",)


@admin.register(AccountFieldType)
class AccountFieldTypeAdmin(admin.ModelAdmin):
    """Manage account field types."""
    list_display = ("name", "state", "description", "date_created")
    list_filter = ("state",)
    search_fields = ("name", "description")
    ordering = ("name",)


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    """Manage payment methods."""
    list_display = ("name", "state", "description", "date_created")
    list_filter = ("state",)
    search_fields = ("name", "description")
    ordering = ("name",)
