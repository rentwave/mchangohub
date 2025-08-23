import csv
import json
from datetime import timedelta, datetime
from decimal import Decimal

from django.contrib import admin
from django.db.models import Sum, Count, Avg, Q
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.db import models

from base.models import State
from .models import WalletAccount, WalletTransaction, WorkflowActionLog, PledgeLog, Pledge, RevenueLog
from .reporting.revenue_analytics import RevenueAnalytics, RevenueReporting


class WorkflowActionLogInline(admin.TabularInline):
    """Inline for viewing workflow actions within transactions."""
    model = WorkflowActionLog
    extra = 0
    readonly_fields = [
        'action_type', 'amount', 'balance_type_before', 'balance_type_after',
        'workflow_step', 'sequence_order', 'description', 'date_created'
    ]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class WalletTransactionInline(admin.TabularInline):
    """Inline for viewing transactions within wallet accounts."""
    model = WalletTransaction
    extra = 0
    readonly_fields = [
        'transaction_type', 'amount', 'charge', 'balance_before', 'balance_after',
        'reference', 'status', 'date_created'
    ]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class DashboardDataMixin:
    """Provides helper methods for dashboard metrics and formatting."""

    def get_account_stats(self):
        """Return account-related metrics."""
        total_accounts = WalletAccount.objects.count()
        active_accounts = WalletAccount.objects.active().count()
        frozen_accounts = WalletAccount.objects.filter(is_frozen=True).count()
        inactive_accounts = total_accounts - active_accounts
        return {
            'total': total_accounts,
            'active': active_accounts,
            'frozen': frozen_accounts,
            'inactive': inactive_accounts
        }

    def get_balance_stats(self):
        """Return aggregated balance metrics."""
        return WalletAccount.objects.aggregate(
            total_current=Sum('current'),
            total_available=Sum('available'),
            total_reserved=Sum('reserved'),
            total_uncleared=Sum('uncleared'),
            avg_balance=Avg('current')
        )

    def get_transaction_stats(self):
        """Return transaction-related metrics."""
        return WalletTransaction.objects.aggregate(
            total_transactions=Count('id'),
            pending_transactions=Count('id', filter=Q(status='pending')),
            completed_transactions=Count('id', filter=Q(status='completed')),
            total_volume=Sum('amount'),
            total_charge=Sum('charge')
        )

    def get_recent_transactions(self, limit=10):
        """Return recent transactions."""
        return WalletTransaction.objects.select_related('wallet_account').order_by('-date_created')[:limit]

    def get_recent_actions(self, limit=10):
        """Return recent workflow actions."""
        return WorkflowActionLog.objects.select_related('wallet_account').order_by('-date_created')[:limit]

    @staticmethod
    def format_currency(currency, amount):
        """Return formatted currency."""
        return f"{currency} {amount:,.2f}" if amount is not None else "-"

    @staticmethod
    def status_badge(status):
        """Return HTML badge for status."""
        colors = {
            'completed': 'green',
            'pending': 'orange',
            'failed': 'red',
            'active': 'green',
            'inactive': 'orange',
            'frozen': 'red'
        }
        if not isinstance(status, str):
            status = status.name
        status_lower = status.lower()
        status_cap = status.capitalize()
        return format_html(
            '<span style="color: {color}; font-weight: bold;">{status}</span>',
            color=colors.get(status_lower, 'black'),
            status=status_cap
        )



@admin.register(WorkflowActionLog)
class WorkflowActionLogAdmin(admin.ModelAdmin, DashboardDataMixin):
    """Admin for workflow action logs."""
    list_display = [
        'wallet_account_display', 'action_type', 'amount_display',
        'workflow_step', 'sequence_order', 'date_created'
    ]
    list_filter = ['action_type', 'workflow_step', 'date_created']
    search_fields = ['wallet_account__account_number', 'reference', 'description']
    readonly_fields = [
        'wallet_account', 'parent_transaction', 'action_type', 'amount',
        'balance_type_before', 'balance_type_after', 'workflow_step',
        'sequence_order', 'reference', 'description', 'metadata'
    ]
    date_hierarchy = 'date_created'
    list_per_page = 50

    def wallet_account_display(self, obj):
        return obj.wallet_account.account_number
    wallet_account_display.short_description = 'Account'

    def amount_display(self, obj):
        return self.format_currency(obj.wallet_account.currency, obj.amount)
    amount_display.short_description = 'Amount'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin, DashboardDataMixin):
    """Admin for wallet transactions."""
    list_display = [
        'wallet_account_display', 'transaction_type', 'amount_display',
        'status_display', 'reference', 'amount_plus_charge' ,'charge', 'balance_before', 'balance_after', 'workflow_actions_count', 'date_created'
    ]
    list_filter = ['transaction_type', 'status', 'date_created']
    search_fields = ['wallet_account__account_number', 'reference', 'description']
    readonly_fields = [
        'wallet_account', 'transaction_type', 'amount', 'balance_before', 'charge', 'amount_plus_charge',
        'balance_after', 'reference', 'description', 'status', 'metadata'
    ]
    inlines = [WorkflowActionLogInline]
    date_hierarchy = 'date_created'
    list_per_page = 50
    
    actions = ['approve_topup_transaction', 'revenue_generated', 'reject_topup_transaction', 'approve_payment_transaction', 'reject_payment_transaction']
    
    def wallet_account_display(self, obj):
        return obj.wallet_account.account_number
    wallet_account_display.short_description = 'Account'
    
    @admin.action(description="Approve selected topups")
    def approve_topup_transaction(self, request, queryset):
        for obj in queryset:
            obj.wallet_account.topup_approved(obj.amount, obj.reference)
    
    @admin.action(description="Reject selected topups")
    def reject_topup_transaction(self, request, queryset):
        for obj in queryset:
            obj.wallet_account.topup_rejected(obj.amount, obj.reference)
    
    @admin.action(description="Approve selected payments")
    def approve_payment_transaction(self, request, queryset):
        for obj in queryset:
            obj.wallet_account.payment_approved(obj.amount, obj.reference)
    
    @admin.action(description="reject selected payments")
    def reject_payment_transaction(self, request, queryset):
        for obj in queryset:
            obj.wallet_account.payment_rejected(obj.amount, obj.reference)

    def revenue_generated(self, obj):
        """Show revenue generated from this transaction."""
        total = obj.revenue_logs.aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
        if total > 0:
            return format_html('<strong style="color: #4caf50;">KES {:,.2f}</strong>', total)
        return "KES 0.00"

    revenue_generated.short_description = "Revenue Generated"
    
    def amount_display(self, obj):
        return self.format_currency(obj.wallet_account.currency, obj.amount)
    amount_display.short_description = 'Amount'

    def status_display(self, obj):
        return self.status_badge(obj.status)
    status_display.short_description = 'Status'

    def workflow_actions_count(self, obj):
        return obj.workflow_actions.count()
    workflow_actions_count.short_description = 'Actions'
    
    def has_add_permission(self, request):
        return False

    # def has_delete_permission(self, request, obj):
    #     return False
from django.urls import path, reverse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.db.models import Sum, Count
from django.utils.html import format_html
from django.contrib import messages
from .models import WalletAccount, WalletTransaction


@admin.register(WalletAccount)
class WalletAccountAdmin(admin.ModelAdmin, DashboardDataMixin):
    list_display = [
        'account_number', 'contribution_display', 'current_display',
        'available_display', 'reserved_display',
        'uncleared_display', 'status_display', 'last_transaction_date'
    ]
    list_filter = ['is_active', 'is_frozen', 'currency', 'last_transaction_date']
    search_fields = ['account_number', 'contribution__name']
    readonly_fields = [
        'account_number', 'current', 'available',
        'reserved', 'uncleared', 'version',
        'last_transaction_date', 'balance_summary_display'
    ]
    actions = ['view_wallet_dashboard', 'freeze_account_action', 'unfreeze_account_action']
    
    
    @admin.action(description="Freeze selected accounts")
    def freeze_account_action(self, request, queryset):
        for account in queryset:
            account.freeze_account()  # calls the model method
        self.message_user(request, f"{queryset.count()} account(s) have been frozen.")

    @admin.action(description="Unfreeze selected accounts")
    def unfreeze_account_action(self, request, queryset):
        for account in queryset:
            account.unfreeze_account()
        self.message_user(request, f"{queryset.count()} account(s) have been unfrozen.")


    def view_wallet_dashboard(self, request, queryset):
        """Redirects admin to wallet detailed dashboard."""
        dashboard_url = reverse('admin:wallet_dashboard')
        return redirect(dashboard_url)
    view_wallet_dashboard.short_description = "View Wallet Detailed Dashboard"

    def contribution_name(self, obj):
        return getattr(obj.contribution, 'name', 'N/A')

    contribution_name.short_description = "Contribution"



    fieldsets = (
        ('Account Information', {
            'fields': ('contribution', 'account_number', 'currency')
        }),
        ('Balance Information', {
            'fields': ('current', 'available', 'reserved',
                       'uncleared', 'balance_summary_display')
        }),
        ('Status & Metadata', {
            'fields': ('is_active', 'is_frozen', 'version', 'last_transaction_date')
        })
    )

    def contribution_display(self, obj):
        return str(obj.contribution)
    contribution_display.short_description = 'Contribution'

    def current_display(self, obj):
        return self.format_currency(obj.currency, obj.current)
    current_display.short_description = 'Current'

    def available_display(self, obj):
        return self.format_currency(obj.currency, obj.available)
    available_display.short_description = 'Available'

    def reserved_display(self, obj):
        return self.format_currency(obj.currency, obj.reserved)
    reserved_display.short_description = 'Reserved'

    def uncleared_display(self, obj):
        return self.format_currency(obj.currency, obj.uncleared)
    uncleared_display.short_description = 'Uncleared'

    def status_display(self, obj):
        if obj.is_frozen:
            return self.status_badge('frozen')
        elif not obj.is_active:
            return self.status_badge('inactive')
        return self.status_badge('active')
    status_display.short_description = 'Status'

    def balance_summary_display(self, obj):
        summary = obj.balance_summary
        html = '''
        <table style="width: 100%; border-collapse: collapse;">
            <tr><td><strong>Current:</strong></td><td>{currency} {current:,.2f}</td></tr>
            <tr><td><strong>Available:</strong></td><td>{currency} {available:,.2f}</td></tr>
            <tr><td><strong>Reserved:</strong></td><td>{currency} {reserved:,.2f}</td></tr>
            <tr><td><strong>Uncleared:</strong></td><td>{currency} {uncleared:,.2f}</td></tr>
        </table>
        '''.format(**summary)
        return format_html(html)
    balance_summary_display.short_description = 'Balance Summary'

    def get_account_stats(self):
        return {
            'total_accounts': WalletAccount.objects.count(),
            'active_accounts': WalletAccount.objects.filter(is_active=True).count(),
            'frozen_accounts': WalletAccount.objects.filter(is_frozen=True).count(),
        }

    def get_balance_stats(self):
        return WalletAccount.objects.aggregate(
            total_current=Sum('current'),
            total_available=Sum('available'),
            total_reserved=Sum('reserved'),
            total_uncleared=Sum('uncleared')
        )

    def get_transaction_stats(self):
        return WalletTransaction.objects.aggregate(
            total_transactions=Count('id'),
            total_amount=Sum('amount'),
            total_charge=Sum('charge')
        )

    def get_recent_transactions(self):
        return WalletTransaction.objects.select_related('wallet_account').order_by('-date_created')[:10]

    def get_recent_actions(self):
        from django.contrib.admin.models import LogEntry
        return LogEntry.objects.select_related('user').order_by('-action_time')[:10]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('dashboard/', self.admin_site.admin_view(self.dashboard_view), name='wallet_dashboard'),
        ]
        return custom_urls + urls

    def dashboard_view(self, request):
        context = dict(
            self.admin_site.each_context(request),
            account_stats=self.get_account_stats(),
            balances=self.get_balance_stats(),
            transactions=self.get_transaction_stats(),
            recent_transactions=self.get_recent_transactions(),
            recent_actions=self.get_recent_actions()
        )
        return TemplateResponse(request, "wallet_dashboard_detailed.html", context)


from django.contrib import admin
from django.utils.html import format_html
from .models import BalanceLog, BalanceLogEntry


class BalanceLogEntryInline(admin.TabularInline):
    """Inline entries under a BalanceLog for quick review."""
    model = BalanceLogEntry
    extra = 0
    readonly_fields = ("entry_type", "account_field_type", "amount_transacted", "state", "date_created")
    can_delete = False
    ordering = ("-date_created",)


@admin.register(BalanceLog)
class BalanceLogAdmin(admin.ModelAdmin):
    """Detailed admin view for Balance Logs."""
    list_display = (
        "balance_entry_type",
        "amount_transacted",
        "total_balance",
        "state",
        "reference",
        "receipt",
        "date_created",
    )
    list_filter = ("balance_entry_type", "state", "date_created")
    search_fields = ("transaction__id", "reference", "receipt", "description")
    readonly_fields = (
        "transaction",
        "balance_entry_type",
        "amount_transacted",
        "total_balance",
        "state",
        "reference",
        "receipt",
        "description",
        "date_created",
    )
    inlines = [BalanceLogEntryInline]
    ordering = ("-date_created",)


@admin.register(BalanceLogEntry)
class BalanceLogEntryAdmin(admin.ModelAdmin):
    """Detailed admin view for Balance Log Entries."""
    list_display = (
        "entry_type",
        "account_field_type",
        "amount_transacted",
        "state",
        "date_created",
    )
    list_filter = ("entry_type", "account_field_type", "state", "date_created")
    search_fields = (
        "process_log__reference",
        "process_log__receipt",
        "process_log__transaction__id",
    )
    readonly_fields = (
        "process_log",
        "entry_type",
        "account_field_type",
        "amount_transacted",
        "state",
        "date_created",
    )
    ordering = ("-date_created",)




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

    state_key = state_name.lower().strip()
    if state_key in color_mapping:
        return color_mapping[state_key]

    for key, color in color_mapping.items():
        if key in state_key or state_key in key:
            return color

    return default_color



class PledgeLogInline(admin.TabularInline):
    """Inline for viewing pledge logs within pledge admin"""
    model = PledgeLog
    extra = 1
    fields = ('amount', 'balance', 'note', 'logged_by', 'date_created')
    readonly_fields = ('balance', 'date_created')



@admin.register(PledgeLog)
class PledgeLogAdmin(admin.ModelAdmin):
    list_display = [
        'pledge_display', 'amount_display', 'balance_display',
        'logged_by', 'date_created', 'note_preview'
    ]
    list_filter = ['date_created', 'logged_by', 'pledge__status']
    search_fields = [
        'pledge__pledger_name', 'note',
    ]
    readonly_fields = ['balance', 'date_created', 'date_modified']
    date_hierarchy = 'date_created'

    fieldsets = (
        ('Payment Information', {
            'fields': ('pledge', 'amount', 'balance')
        }),
        ('Details', {
            'fields': ('note', 'logged_by')
        }),
        ('Timestamps', {
            'fields': ('date_created', 'date_modified'),
            'classes': ('collapse',)
        }),
    )

    def pledge_display(self, obj):
        return f"{obj.pledge.pledger_name} ({obj.pledge.amount:,.2f})"
    pledge_display.short_description = "Pledge"
    pledge_display.admin_order_field = 'pledge__pledger_name'

    def amount_display(self, obj):
        return f"KES {obj.amount:,.2f}"
    amount_display.short_description = "Payment"
    amount_display.admin_order_field = 'amount'

    def balance_display(self, obj):
        balance = Decimal(obj.balance) if not isinstance(obj.balance, Decimal) else obj.balance
        amount = Decimal(obj.pledge.amount) if not isinstance(obj.pledge.amount, Decimal) else obj.pledge.amount

        if balance <= 0:
            color = "green"
        elif balance < amount * Decimal("0.5"):
            color = "orange"
        else:
            color = "red"

        formatted_balance = f"KES {balance:,.2f}"

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            formatted_balance
        )

    balance_display.short_description = "Remaining Balance"
    balance_display.admin_order_field = "balance"

    def note_preview(self, obj):
        return (obj.note[:50] + '...') if obj.note and len(obj.note) > 50 else (obj.note or "-")
    note_preview.short_description = "Note"


@admin.register(Pledge)
class PledgeAdmin(admin.ModelAdmin):
    list_display = [
        'pledger_name', 'amount_display', 'status_display',
        'balance_display', 'progress_bar', 'planned_clear_date',
        'raised_by', 'date_created'
    ]
    list_filter = ['status', 'planned_clear_date', 'raised_by', 'date_created']
    search_fields = [
        'pledger_name', 'pledger_contact', 'purpose',
    ]
    readonly_fields = [
        'total_paid_display', 'balance_display_detailed', 'progress_percentage',
        'date_created', 'date_modified', 'logs_summary'
    ]
    date_hierarchy = 'date_created'
    actions = [
        'mark_as_cleared', 'mark_as_pending', 'clear_pledges_action',
        'export_selected_pledges', 'send_reminder_emails'
    ]
    inlines = [PledgeLogInline]

    fieldsets = (
        ('Pledger Information', {
            'fields': ('pledger_name', 'pledger_contact', 'raised_by')
        }),
        ('Pledge Details', {
            'fields': ('contribution', 'amount', 'purpose', 'planned_clear_date', 'status')
        }),
        ('Payment Summary', {
            'fields': (
                'total_paid_display', 'balance_display_detailed',
                'progress_percentage', 'logs_summary'
            ),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('date_created', 'date_modified'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'status',
        ).prefetch_related('logs')

    def amount_display(self, obj):
        return f"KES {obj.amount:,.2f}"
    amount_display.short_description = "Pledge Amount"
    amount_display.admin_order_field = 'amount'

    def status_display(self, obj):
        color = getattr(obj.status, 'color', None) or get_state_color(obj.status.name)
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; '
            'border-radius: 3px; font-weight: bold; font-size: 11px;">{}</span>',
            color, obj.status.name
        )
    status_display.short_description = "Status"
    status_display.admin_order_field = 'status__name'

    def balance_display(self, obj):
        balance = obj.balance
        amount = obj.amount

        if balance <= 0:
            color = "green"
        elif balance < amount * Decimal("0.5"):
            color = "orange"
        else:
            color = "red"

        formatted_balance = f"KES {float(balance):,.2f}"

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            formatted_balance
        )

    balance_display.short_description = "Balance"

    def balance_display_detailed(self, obj):
        balance = obj.balance
        total_paid = obj.total_paid
        percentage = (total_paid / obj.amount * 100) if obj.amount > 0 else 0
        return format_html(
            '<div><strong>Remaining:</strong> KES {:,.2f}<br>'
            '<strong>Paid:</strong> KES {:,.2f} ({:.1f}%)</div>',
            balance, total_paid, percentage
        )

    balance_display_detailed.short_description = "Payment Details"

    def progress_bar(self, obj):
        amount = obj.amount
        balance = obj.balance
        paid = amount - balance
        percent = (paid / amount * 100) if amount > 0 else 0

        percent_str = f"{percent:.1f}%"

        return format_html(
            '<div style="width:100px; border:1px solid #ccc; background:#eee;">'
            '  <div style="width:{}%; background-color:#4CAF50; height:12px;"></div>'
            '</div>'
            '<span style="font-size:11px; margin-left:4px;">{}</span>',
            percent,  # for width
            percent_str  # for label
        )

    progress_bar.short_description = "Progress"

    def progress_percentage(self, obj):
        total_paid = obj.total_paid
        percentage = (total_paid / obj.amount * 100) if obj.amount > 0 else 0
        return f"{percentage:.1f}%"
    progress_percentage.short_description = "Payment Progress"

    def total_paid_display(self, obj):
        total_paid = obj.total_paid
        return f"KES {total_paid:,.2f}"

    total_paid_display.short_description = "Total Paid"
    total_paid_display.admin_order_field = "total_paid"

    def logs_summary(self, obj):
        logs_count = obj.logs.count()
        if logs_count == 0:
            return "No payments recorded"
        last_payment = obj.logs.first()
        return format_html(
            '<strong>{}</strong> payment(s)<br>Last: KES {:,.2f} on {}',
            logs_count,
            last_payment.amount if last_payment else 0,
            last_payment.date_created.strftime('%Y-%m-%d') if last_payment else 'N/A'
        )
    logs_summary.short_description = "Payment History"

    @admin.action(description='Mark selected pledges as cleared')
    def mark_as_cleared(self, request, queryset):
        try:
            cleared_state = State.objects.get(name='Cleared')
            updated = queryset.update(status=cleared_state)
            self.message_user(request, f'Successfully marked {updated} pledge(s) as cleared.', messages.SUCCESS)
        except State.DoesNotExist:
            self.message_user(request, 'Error: "Cleared" status not found in database.', messages.ERROR)

    @admin.action(description='Mark selected pledges as pending')
    def mark_as_pending(self, request, queryset):
        try:
            pending_state = State.objects.get(name='Pending')
            updated = queryset.update(status=pending_state)
            self.message_user(request, f'Successfully marked {updated} pledge(s) as pending.', messages.SUCCESS)
        except State.DoesNotExist:
            self.message_user(request, 'Error: "Pending" status not found in database.', messages.ERROR)

    @admin.action(description='Clear selected pledges (add full payment)')
    def clear_pledges_action(self, request, queryset):
        cleared_count = 0
        for pledge in queryset:
            remaining_balance = pledge.balance()
            if remaining_balance > 0:
                pledge.add_payment(amount=remaining_balance, user=request.user, note="Admin bulk clear action")
                cleared_count += 1
        self.message_user(request, f'Successfully cleared {cleared_count} pledge(s) with remaining balances.', messages.SUCCESS)

class PledgeStatusFilter(admin.SimpleListFilter):
    """Custom filter for pledge status with color indicators"""
    title = 'Status with Colors'
    parameter_name = 'status_colored'

    def lookups(self, request, model_admin):
        states = State.objects.all()
        choices = []
        for state in states:
            if hasattr(state, 'color') and state.color:
                color = state.color
            else:
                color = get_state_color(state.name)
            label = f"{state.name} ●"
            choices.append((state.id, label))
        return choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(status__id=self.value())
        return queryset


from decimal import Decimal
from django.contrib import admin
from django.db import models, connection
from django.db.models import Sum, Count, Q, Avg, Min, Max
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html, mark_safe
from django.utils import timezone
from django.template.response import TemplateResponse
from django.contrib import messages
from datetime import datetime, timedelta
import json
import csv

from billing.models import RevenueLog, WalletAccount, WalletTransaction


class RevenueAdminMixin:
    """
    Mixin for Django admin to add revenue-related functionality.
    """

    def get_daily_revenue_summary(self, obj):
        """Admin method to show daily revenue summary."""
        if hasattr(obj, 'date_created'):
            date = obj.date_created.date()
            summary = RevenueLog.objects.daily_revenue_summary(date)
            return f"KES {summary['total']:,.2f}"
        return "N/A"

    get_daily_revenue_summary.short_description = "Daily Revenue"

    def get_charge_rate_display(self, obj):
        """Admin method to display charge rate as percentage."""
        if hasattr(obj, 'charge_rate') and obj.charge_rate:
            return f"{float(obj.charge_rate * 100):.2f}%"
        return "N/A"

    get_charge_rate_display.short_description = "Charge Rate"

    def get_revenue_status(self, obj):
        """Admin method to display revenue status from metadata."""
        if hasattr(obj, 'metadata') and obj.metadata:
            status = obj.metadata.get('status', 'unknown')
            colors = {
                'pending': '#ff9800',  # Orange
                'realized': '#4caf50',  # Green
                'unrealized': '#f44336',  # Red
                'unknown': '#9e9e9e'  # Gray
            }
            color = colors.get(status, '#9e9e9e')
            return format_html(
                '<span style="color: {}; font-weight: bold;">{}</span>',
                color,
                status.title()
            )
        return "Unknown"

    get_revenue_status.short_description = "Status"


@admin.register(RevenueLog)
class RevenueLogAdmin(admin.ModelAdmin, RevenueAdminMixin):
    list_display = [
        'reference', 'revenue_type', 'formatted_amount', 'formatted_original_amount',
        'get_charge_rate_display', 'get_revenue_status', 'wallet_account_display', 'date_created'
    ]
    list_filter = [
        'revenue_type',
        'date_created',
        ('wallet_account__contribution', admin.RelatedOnlyFieldListFilter),
    ]
    search_fields = [
        'reference', 'description', 'parent_transaction__reference',
        'wallet_account__account_number', 'wallet_account__contribution__name'
    ]
    readonly_fields = ['date_created', 'date_modified']
    raw_id_fields = ['wallet_account', 'parent_transaction']
    date_hierarchy = 'date_created'

    # Enhanced actions for analytics
    actions = ['view_analytics_dashboard', 'view_detailed_breakdown']

    fieldsets = (
        (None, {
            'fields': ('wallet_account', 'parent_transaction', 'revenue_type')
        }),
        ('Amount Details', {
            'fields': ('amount', 'original_amount', 'charge_rate')
        }),
        ('Reference & Description', {
            'fields': ('reference', 'description')
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('date_created', 'date_modified'),
            'classes': ('collapse',)
        })
    )

    class Media:
        css = {
            'all': ('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css',)
        }

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'wallet_account', 'wallet_account__contribution', 'parent_transaction'
        )

    def view_analytics_dashboard(self, request, queryset):
        """Redirect to comprehensive analytics dashboard."""
        # Store queryset IDs in session for the analytics view
        queryset_ids = list(queryset.values_list('id', flat=True))
        request.session['analytics_queryset_ids'] = queryset_ids

        analytics_url = reverse('admin:revenue_analytics_dashboard')
        return HttpResponseRedirect(analytics_url)

    view_analytics_dashboard.short_description = "📊 View Analytics Dashboard"

    def view_detailed_breakdown(self, request, queryset):
        """Redirect to detailed breakdown view."""
        queryset_ids = list(queryset.values_list('id', flat=True))
        request.session['breakdown_queryset_ids'] = queryset_ids

        breakdown_url = reverse('admin:revenue_detailed_breakdown')
        return HttpResponseRedirect(breakdown_url)

    view_detailed_breakdown.short_description = "💼 View Detailed Breakdown"

    def formatted_amount(self, obj):
        from decimal import Decimal
        amount = obj.amount
        if not isinstance(amount, Decimal):
            try:
                amount = Decimal(str(amount))
            except Exception:
                amount = Decimal("0.00")

        formatted = f"{amount:,.2f}"
        return format_html("<strong>KES {}</strong>", formatted)

    formatted_amount.short_description = "Revenue Amount"
    formatted_amount.admin_order_field = 'amount'

    def formatted_original_amount(self, obj):
        """Display original amount with proper formatting."""
        from decimal import Decimal
        amount = obj.original_amount
        if not isinstance(amount, Decimal):
            try:
                amount = Decimal(str(amount))
            except Exception:
                amount = Decimal("0.00")

        formatted = f"{amount:,.2f}"
        return format_html("KES {}", formatted)

    formatted_original_amount.short_description = "Original Amount"
    formatted_original_amount.admin_order_field = 'original_amount'

    # def formatted_total_revenue(self, obj):
    #     """Display the total accumulated revenue (wallet balance)."""
    #     try:
    #         total = RevenueLog.objects.first()
    #         amount = total.amount if total else Decimal("0.00")
    #     except Exception:
    #         amount = Decimal("0.00")
    #
    #     return format_html("KES {:,.2f}", amount)
    #
    # formatted_total_revenue.short_description = "Total Revenue"

    # formatted_total_revenue.short_description = "Total Revenue"

    def wallet_account_display(self, obj):
        """Display wallet account info."""
        return format_html(
            '<a href="/admin/your_app/walletaccount/{}/change/">{}</a><br>'
            '<small style="color: #666;">{}</small>',
            obj.wallet_account.id,
            obj.wallet_account.account_number,
            obj.wallet_account.contribution.name if hasattr(obj.wallet_account.contribution, 'name') else 'N/A'
        )

    wallet_account_display.short_description = "Wallet Account"

    def changelist_view(self, request, extra_context=None):
        """Enhanced changelist with revenue summary."""
        response = super().changelist_view(request, extra_context=extra_context)

        try:
            qs = response.context_data['cl'].queryset
            summary = qs.aggregate(
                total_revenue=Sum('amount'),
                total_count=Count('id'),
                avg_revenue=Avg('amount'),
                topup_revenue=Sum('amount', filter=Q(revenue_type='topup_charge')),
                withdrawal_revenue=Sum('amount', filter=Q(revenue_type='withdrawal_charge')),
                topup_count=Count('id', filter=Q(revenue_type='topup_charge')),
                withdrawal_count=Count('id', filter=Q(revenue_type='withdrawal_charge')),
            )

            for key, value in summary.items():
                if value is None:
                    summary[key] = Decimal('0.00') if 'revenue' in key or 'avg' in key else 0

            response.context_data['summary'] = summary

        except (AttributeError, KeyError):
            pass

        return response

    def get_urls(self):
        """Add custom URLs for analytics views."""
        urls = super().get_urls()
        custom_urls = [
            path('analytics-dashboard/', self.admin_site.admin_view(self.analytics_dashboard_view),
                 name='revenue_analytics_dashboard'),
            path('detailed-breakdown/', self.admin_site.admin_view(self.detailed_breakdown_view),
                 name='revenue_detailed_breakdown'),
            path('export-analytics/', self.admin_site.admin_view(self.export_analytics_csv),
                 name='revenue_export_analytics'),
        ]
        return custom_urls + urls

    def get_database_compatible_queries(self, queryset):
        """Get database-compatible queries for different DB engines."""
        db_vendor = connection.vendor

        if db_vendor == 'sqlite':
            # SQLite-compatible queries
            daily_data = queryset.extra(
                select={'day': "date(date_created)"}
            ).values('day').annotate(
                daily_revenue=Sum('amount'),
                daily_count=Count('id')
            ).order_by('-day')[:7]

            weekly_data = []  # Skip weekly for SQLite simplicity

        elif db_vendor == 'mysql':
            # MySQL-compatible queries
            daily_data = queryset.extra(
                select={'day': "DATE(date_created)"}
            ).values('day').annotate(
                daily_revenue=Sum('amount'),
                daily_count=Count('id')
            ).order_by('-day')[:7]

            weekly_data = queryset.extra(
                select={
                    'week': 'YEARWEEK(date_created)',
                    'week_start': 'DATE_SUB(date_created, INTERVAL WEEKDAY(date_created) DAY)'
                }
            ).values('week', 'week_start').annotate(
                weekly_revenue=Sum('amount'),
                weekly_count=Count('id')
            ).order_by('-week')[:4]

        else:  # PostgreSQL and others
            daily_data = queryset.extra(
                select={'day': "date_trunc('day', date_created)::date"}
            ).values('day').annotate(
                daily_revenue=Sum('amount'),
                daily_count=Count('id')
            ).order_by('-day')[:7]

            weekly_data = queryset.extra(
                select={
                    'week': "date_trunc('week', date_created)::date"
                }
            ).values('week').annotate(
                weekly_revenue=Sum('amount'),
                weekly_count=Count('id')
            ).order_by('-week')[:4]

        return daily_data, weekly_data

    def analytics_dashboard_view(self, request):
        """Comprehensive analytics dashboard with tables and charts."""
        # Get queryset from session or use all records
        queryset_ids = request.session.get('analytics_queryset_ids')
        if queryset_ids:
            queryset = RevenueLog.objects.filter(id__in=queryset_ids)
            request.session.pop('analytics_queryset_ids', None)  # Clear after use
        else:
            queryset = RevenueLog.objects.all()

        total_records = queryset.count()

        # Basic analytics
        analytics = queryset.aggregate(
            total_revenue=Sum('amount'),
            total_count=Count('id'),
            avg_revenue=Avg('amount'),
            max_revenue=Max('amount'),
            min_revenue=Min('amount'),
            topup_revenue=Sum('amount', filter=Q(revenue_type='topup_charge')),
            withdrawal_revenue=Sum('amount', filter=Q(revenue_type='withdrawal_charge')),
            adjustment_revenue=Sum('amount', filter=Q(revenue_type='adjustment')),
            topup_count=Count('id', filter=Q(revenue_type='topup_charge')),
            withdrawal_count=Count('id', filter=Q(revenue_type='withdrawal_charge')),
            adjustment_count=Count('id', filter=Q(revenue_type='adjustment')),
        )

        # Handle None values
        for key, value in analytics.items():
            if value is None:
                analytics[key] = Decimal(
                    '0.00') if 'revenue' in key or 'avg' in key or 'max' in key or 'min' in key else 0

        # Status breakdown
        status_breakdown = []
        status_data = {}
        for log in queryset:
            status = log.metadata.get('status', 'unknown') if log.metadata else 'unknown'
            if status not in status_data:
                status_data[status] = {'count': 0, 'amount': Decimal('0.00')}
            status_data[status]['count'] += 1
            status_data[status]['amount'] += log.amount

        for status, data in status_data.items():
            percentage = (data['count'] / total_records * 100) if total_records > 0 else 0
            status_breakdown.append({
                'status': status.title(),
                'count': data['count'],
                'amount': data['amount'],
                'percentage': percentage
            })

        # Top accounts
        top_accounts = queryset.values(
            'wallet_account__account_number',
            'wallet_account__contribution__name'
        ).annotate(
            total_revenue=Sum('amount'),
            transaction_count=Count('id'),
            avg_revenue=Avg('amount')
        ).order_by('-total_revenue')[:10]

        # Revenue by type for charts
        revenue_by_type = [
            {
                'type': 'TopUp Charges',
                'amount': float(analytics['topup_revenue']),
                'count': analytics['topup_count'],
                'color': '#4CAF50'
            },
            {
                'type': 'Withdrawal Charges',
                'amount': float(analytics['withdrawal_revenue']),
                'count': analytics['withdrawal_count'],
                'color': '#FF9800'
            },
            {
                'type': 'Adjustments',
                'amount': float(analytics['adjustment_revenue']),
                'count': analytics['adjustment_count'],
                'color': '#2196F3'
            }
        ]

        # Get time-based data
        daily_data, weekly_data = self.get_database_compatible_queries(queryset)

        # Prepare chart data
        chart_data = {
            'revenue_by_type': revenue_by_type,
            'daily_trend': [
                {
                    'date': str(day['day']),
                    'revenue': float(day['daily_revenue']),
                    'count': day['daily_count']
                }
                for day in daily_data
            ],
            'status_distribution': [
                {
                    'status': item['status'],
                    'amount': float(item['amount']),
                    'count': item['count']
                }
                for item in status_breakdown
            ]
        }

        context = {
            'title': 'Revenue Analytics Dashboard',
            'subtitle': f'Analysis of {total_records:,} revenue records',
            'analytics': analytics,
            'status_breakdown': status_breakdown,
            'top_accounts': top_accounts,
            'revenue_by_type': revenue_by_type,
            'daily_data': daily_data,
            'weekly_data': weekly_data,
            'chart_data': json.dumps(chart_data),
            'total_records': total_records,
            'opts': self.model._meta,
            'has_view_permission': True,
        }

        return TemplateResponse(request, 'admin/revenue_analytics_dashboard.html', context)

    def detailed_breakdown_view(self, request):
        """Detailed breakdown view with comprehensive tables."""
        queryset_ids = request.session.get('breakdown_queryset_ids')
        if queryset_ids:
            queryset = RevenueLog.objects.filter(id__in=queryset_ids)
            request.session.pop('breakdown_queryset_ids', None)
        else:
            queryset = RevenueLog.objects.all()

        total_records = queryset.count()

        monthly_data = (
            queryset
            .annotate(month=TruncMonth("date_created"))
            .values("month")
            .annotate(
                monthly_revenue=Sum("amount"),
                monthly_count=Count("id"),
                avg_daily_revenue=Sum("amount") / 30.0
            )
            .order_by("-month")[:6]
        )

        type_breakdown = queryset.values('revenue_type').annotate(
            type_revenue=Sum('amount'),
            type_count=Count('id'),
            avg_amount=Avg('amount'),
            max_amount=Max('amount'),
            min_amount=Min('amount')
        ).order_by('-type_revenue')

        account_performance = queryset.values(
            'wallet_account__account_number',
            'wallet_account__contribution__name'
        ).annotate(
            total_revenue=Sum('amount'),
            transaction_count=Count('id'),
            avg_revenue=Avg('amount'),
            last_transaction=Max('date_created')
        ).order_by('-total_revenue')[:20]

        thirty_days_ago = timezone.now().date() - timedelta(days=30)
        daily_performance = queryset.filter(
            date_created__date__gte=thirty_days_ago
        ).extra(
            select={'day': "date(date_created)" if connection.vendor == 'sqlite' else "DATE(date_created)"}
        ).values('day').annotate(
            daily_revenue=Sum('amount'),
            daily_count=Count('id')
        ).order_by('-day')

        context = {
            'title': 'Detailed Revenue Breakdown',
            'subtitle': f'Comprehensive analysis of {total_records:,} revenue records',
            'monthly_data': monthly_data,
            'type_breakdown': type_breakdown,
            'account_performance': account_performance,
            'daily_performance': daily_performance,
            'total_records': total_records,
            'opts': self.model._meta,
            'has_view_permission': True,
        }

        return TemplateResponse(request, 'admin/revenue_detailed_breakdown.html', context)

    def export_analytics_csv(self, request):
        """Export analytics summary to CSV."""
        queryset = self.get_queryset(request)

        response = HttpResponse(content_type='text/csv')
        response[
            'Content-Disposition'] = f'attachment; filename="revenue_analytics_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'

        writer = csv.writer(response)

        writer.writerow(['REVENUE ANALYTICS SUMMARY'])
        writer.writerow(['Generated on:', timezone.now().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow(['Total Records:', queryset.count()])
        writer.writerow([])

        # Write detailed data
        writer.writerow([
            'Date', 'Reference', 'Revenue Type', 'Amount', 'Original Amount',
            'Charge Rate', 'Status', 'Account Number', 'Contribution', 'Description'
        ])

        for log in queryset.select_related('wallet_account', 'wallet_account__contribution'):
            writer.writerow([
                log.date_created.strftime('%Y-%m-%d %H:%M:%S'),
                log.reference,
                log.get_revenue_type_display() if hasattr(log, 'get_revenue_type_display') else log.revenue_type,
                float(log.amount),
                float(log.original_amount),
                f"{float(log.charge_rate * 100):.2f}%" if log.charge_rate else 'N/A',
                log.metadata.get('status', 'unknown') if log.metadata else 'unknown',
                log.wallet_account.account_number,
                getattr(log.wallet_account.contribution, 'name', 'N/A'),
                log.description
            ])

        return response


class RevenueAdminSite(admin.AdminSite):
    site_header = "Revenue Management Dashboard"
    site_title = "Revenue Admin"
    index_title = "Revenue Analytics & Management"

    def index(self, request, extra_context=None):
        """Enhanced admin index with revenue overview."""
        extra_context = extra_context or {}

        today_summary = RevenueLog.objects.daily_revenue_summary()

        today = timezone.now().date()
        month_start = today.replace(day=1)
        month_summary = RevenueAnalytics.get_revenue_summary(month_start, today)

        pending_vs_realized = RevenueAnalytics.get_pending_vs_realized_revenue()

        extra_context.update({
            'today_revenue': today_summary,
            'month_revenue': month_summary,
            'pending_vs_realized': pending_vs_realized,
            'total_accounts': WalletAccount.objects.filter(is_active=True).count(),
            'total_transactions_today': WalletTransaction.objects.filter(
                date_created__date=today
            ).count(),
        })

        return super().index(request, extra_context)


revenue_admin = RevenueAdminSite(name='revenue_admin')
revenue_admin.register(RevenueLog, RevenueLogAdmin)