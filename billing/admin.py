from django.contrib import admin
from django.db.models import Sum, Count, Avg, Q
from django.utils.html import format_html
from django.urls import path
from django.template.response import TemplateResponse
from .models import WalletAccount, WalletTransaction, WorkflowActionLog

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
        'transaction_type', 'amount', 'balance_before', 'balance_after',
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
            total_current=Sum('current_balance'),
            total_available=Sum('available_balance'),
            total_reserved=Sum('reserved_balance'),
            total_uncleared=Sum('uncleared_balance'),
            avg_balance=Avg('current_balance')
        )

    def get_transaction_stats(self):
        """Return transaction-related metrics."""
        return WalletTransaction.objects.aggregate(
            total_transactions=Count('id'),
            pending_transactions=Count('id', filter=Q(status='pending')),
            completed_transactions=Count('id', filter=Q(status='completed')),
            total_volume=Sum('amount')
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
        return format_html(
            '<span style="color: {color}; font-weight: bold;">{status}</span>',
            color=colors.get(status.lower(), 'black'),
            status=status.capitalize()
        )



@admin.register(WorkflowActionLog)
class WorkflowActionLogAdmin(admin.ModelAdmin, DashboardDataMixin):
    """Admin for workflow action logs."""
    list_display = [
        'id', 'wallet_account_display', 'action_type', 'amount_display',
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
        'status_display', 'reference', 'workflow_actions_count', 'date_created'
    ]
    list_filter = ['transaction_type', 'status', 'date_created']
    search_fields = ['wallet_account__account_number', 'reference', 'description']
    readonly_fields = [
        'wallet_account', 'transaction_type', 'amount', 'balance_before',
        'balance_after', 'reference', 'description', 'status', 'metadata'
    ]
    inlines = [WorkflowActionLogInline]
    date_hierarchy = 'date_created'
    list_per_page = 50
    
    actions = ['approve_topup_transaction', 'reject_topup_transaction', 'approve_payment_transaction', 'reject_payment_transaction']
    
    def wallet_account_display(self, obj):
        return obj.wallet_account.account_number
    wallet_account_display.short_description = 'Account'
    
    def approve_topup_transaction(self, obj):
        return obj.account.approve_topup(obj.amount, obj.reference, "Manual Approval")
    
    def reject_topup_transaction(self, obj):
        return obj.account.reject_topup(obj.amount, obj.reference, "Manual Rejection")
    
    def approve_payment_transaction(self, obj):
        return obj.account.approve_payment(obj.amount, obj.reference, "Manual Approval")
    
    def reject_payment_transaction(self, obj):
        return obj.account.reject_payment(obj.amount, obj.reference, "Manual Rejection")
    
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
        'account_number', 'contribution_display', 'current_balance_display',
        'available_balance_display', 'reserved_balance_display',
        'uncleared_balance_display', 'status_display', 'last_transaction_date'
    ]
    list_filter = ['is_active', 'is_frozen', 'currency', 'last_transaction_date']
    search_fields = ['account_number', 'contribution__name']
    readonly_fields = [
        'account_number', 'current_balance', 'available_balance',
        'reserved_balance', 'uncleared_balance', 'version',
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

    fieldsets = (
        ('Account Information', {
            'fields': ('contribution', 'account_number', 'currency')
        }),
        ('Balance Information', {
            'fields': ('current_balance', 'available_balance', 'reserved_balance',
                       'uncleared_balance', 'balance_summary_display')
        }),
        ('Status & Metadata', {
            'fields': ('is_active', 'is_frozen', 'version', 'last_transaction_date')
        })
    )

    def contribution_display(self, obj):
        return str(obj.contribution)
    contribution_display.short_description = 'Contribution'

    def current_balance_display(self, obj):
        return self.format_currency(obj.currency, obj.current_balance)
    current_balance_display.short_description = 'Current'

    def available_balance_display(self, obj):
        return self.format_currency(obj.currency, obj.available_balance)
    available_balance_display.short_description = 'Available'

    def reserved_balance_display(self, obj):
        return self.format_currency(obj.currency, obj.reserved_balance)
    reserved_balance_display.short_description = 'Reserved'

    def uncleared_balance_display(self, obj):
        return self.format_currency(obj.currency, obj.uncleared_balance)
    uncleared_balance_display.short_description = 'Uncleared'

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
            total_current=Sum('current_balance'),
            total_available=Sum('available_balance'),
            total_reserved=Sum('reserved_balance'),
            total_uncleared=Sum('uncleared_balance')
        )

    def get_transaction_stats(self):
        return WalletTransaction.objects.aggregate(
            total_transactions=Count('id'),
            total_amount=Sum('amount')
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
        "id",
        "transaction_link",
        "balance_entry_type",
        "amount_transacted",
        "total_balance",
        "state",
        "reference",
        "receipt",
        "short_description",
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

    def transaction_link(self, obj):
        """Clickable transaction link to related WalletTransaction."""
        return format_html('<a href="/admin/billing/wallettransaction/{}/change/">{}</a>',
                           obj.transaction.id, obj.transaction)
    transaction_link.short_description = "Transaction"

    def short_description(self, obj):
        """Truncate description to keep list view clean."""
        return (obj.description[:50] + "...") if obj.description and len(obj.description) > 50 else obj.description
    short_description.short_description = "Description"


@admin.register(BalanceLogEntry)
class BalanceLogEntryAdmin(admin.ModelAdmin):
    """Detailed admin view for Balance Log Entries."""
    list_display = (
        "id",
        "process_log_link",
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

    def process_log_link(self, obj):
        """Clickable link to related BalanceLog."""
        return format_html('<a href="/admin/billing/balancelog/{}/change/">{}</a>',
                           obj.process_log.id, obj.process_log)
    process_log_link.short_description = "Balance Log"


def export_balance_logs(modeladmin, request, queryset):
    """Export selected logs to CSV."""
    import csv
    from django.http import HttpResponse
    response = HttpResponse(content_type="text/csv")
    response['Content-Disposition'] = 'attachment; filename="balance_logs.csv"'
    writer = csv.writer(response)
    writer.writerow(["ID", "Transaction", "Entry Type", "Amount", "Total Balance", "State", "Date Created"])
    for log in queryset:
        writer.writerow([
            log.id,
            str(log.transaction),
            str(log.balance_entry_type),
            log.amount_transacted,
            log.total_balance,
            str(log.state),
            log.date_created
        ])
    return response

export_balance_logs.short_description = "Export selected balance logs to CSV"
BalanceLogAdmin.actions = [export_balance_logs]
