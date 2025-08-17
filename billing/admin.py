from decimal import Decimal

from django.contrib import admin
from django.db.models import Sum, Count, Avg, Q
from django.utils.html import format_html
from django.urls import path
from django.template.response import TemplateResponse

from base.models import State
from .models import WalletAccount, WalletTransaction, WorkflowActionLog, PledgeLog, Pledge


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
        'status_display', 'reference', 'charge', 'balance_before', 'balance_after', 'workflow_actions_count', 'date_created'
    ]
    list_filter = ['transaction_type', 'status', 'date_created']
    search_fields = ['wallet_account__account_number', 'reference', 'description']
    readonly_fields = [
        'wallet_account', 'transaction_type', 'amount', 'balance_before', 'charge',
        'balance_after', 'reference', 'description', 'status', 'metadata'
    ]
    inlines = [WorkflowActionLogInline]
    date_hierarchy = 'date_created'
    list_per_page = 50
    
    actions = ['approve_topup_transaction', 'reject_topup_transaction', 'approve_payment_transaction', 'reject_payment_transaction']
    
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


