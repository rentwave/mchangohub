from django.contrib import admin
from django.utils.html import format_html
from .models import (
    State, BalanceEntryType, ExecutionProfile, RuleProfile, RuleProfileCommand,
    EntryType, AccountFieldType, PaymentMethod
)


@admin.register(State)
class StateAdmin(admin.ModelAdmin):
    """Manage lifecycle states."""
    list_display = ("id", "name", "date_created", "date_modified")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(BalanceEntryType)
class BalanceEntryTypeAdmin(admin.ModelAdmin):
    """Manage balance entry types."""
    list_display = ("id", "name", "description", "date_created")
    search_fields = ("name", "description")
    ordering = ("name",)


@admin.register(ExecutionProfile)
class ExecutionProfileAdmin(admin.ModelAdmin):
    """Manage execution profiles."""
    list_display = ("id", "name", "description", "date_created")
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
    list_display = ("id", "execution_profile_link", "name", "order", "sleep_seconds", "date_created")
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
    list_display = ("id", "name", "rule_profile_link", "state", "order", "date_created")
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
    list_display = ("id", "name", "description", "date_created")
    search_fields = ("name", "description")
    ordering = ("name",)


@admin.register(AccountFieldType)
class AccountFieldTypeAdmin(admin.ModelAdmin):
    """Manage account field types."""
    list_display = ("id", "name", "state", "description", "date_created")
    list_filter = ("state",)
    search_fields = ("name", "description")
    ordering = ("name",)


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    """Manage payment methods."""
    list_display = ("id", "name", "state", "description", "date_created")
    list_filter = ("state",)
    search_fields = ("name", "description")
    ordering = ("name",)
