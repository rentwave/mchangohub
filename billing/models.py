from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from decimal import Decimal, ROUND_UP
import logging
from typing import Dict, List, Optional
from enum import Enum

from django.utils.html import format_html

from base.models import BaseModel, State, EntryType, AccountFieldType, BalanceEntryType
from billing.helpers.generate_unique_ref import TransactionRefGenerator
from contributions.models import Contribution
from users.models import User

logger = logging.getLogger(__name__)


class WorkflowActionType(models.TextChoices):
    """Enum for workflow action types"""
    MONEY_TO_UNCLEARED = 'money_to_uncleared', 'Money Added to Uncleared'
    MONEY_TO_CURRENT = 'money_to_current', 'Money Added to Current'
    MONEY_FROM_UNCLEARED = 'money_from_uncleared', 'Money Deducted from Uncleared'
    MONEY_TO_AVAILABLE = 'money_to_available', 'Money Added to Available'
    MONEY_FROM_AVAILABLE = 'money_from_available', 'Money Deducted from Available'
    MONEY_TO_RESERVED = 'money_to_reserved', 'Money Added to Reserved'
    MONEY_FROM_RESERVED = 'money_from_reserved', 'Money Deducted from Reserved'
    MONEY_FROM_CURRENT = 'money_from_current', 'Money Deducted from Current'
    MONEY_FOR_WITHDRAWAL = 'money_for_withdrawal', 'Money Prepared for Withdrawal'
    CHARGE_DEDUCTED = 'charge_deducted', 'Charge Deducted for Withdrawal'


class RevenueType(models.TextChoices):
    """Types of revenue sources"""
    TOPUP_CHARGE = 'topup_charge', 'TopUp Charge'
    WITHDRAWAL_CHARGE = 'withdrawal_charge', 'Withdrawal Charge'
    ADJUSTMENT = 'adjustment', 'Manual Adjustment'


class RevenueLogManager(models.Manager):
    """Custom manager for RevenueLog with useful query methods."""

    def by_type(self, revenue_type):
        """Filter by revenue type."""
        return self.filter(revenue_type=revenue_type)

    def for_date_range(self, start_date, end_date):
        """Get revenue for a specific date range."""
        return self.filter(date_created__range=[start_date, end_date])

    def total_revenue(self):
        """Get total revenue across all sources."""
        return self.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

    def daily_revenue_summary(self, date=None):
        """Get revenue summary for a specific date (default: today)."""
        if date is None:
            date = timezone.now().date()

        daily_revenue = self.filter(date_created__date=date).aggregate(
            topup_charges=models.Sum('amount', filter=models.Q(revenue_type='topup_charge')),
            withdrawal_charges=models.Sum('amount', filter=models.Q(revenue_type='withdrawal_charge')),
            adjustments=models.Sum('amount', filter=models.Q(revenue_type='adjustment')),
            total=models.Sum('amount')
        )

        return {
            'date': date,
            'topup_charges': daily_revenue['topup_charges'] or Decimal('0.00'),
            'withdrawal_charges': daily_revenue['withdrawal_charges'] or Decimal('0.00'),
            'adjustments': daily_revenue['adjustments'] or Decimal('0.00'),
            'total': daily_revenue['total'] or Decimal('0.00')
        }


class RevenueLog(BaseModel):
    """
    Tracks all revenue generated from charges.
    This table logs every charge deducted as our revenue source.
    """
    wallet_account = models.ForeignKey('WalletAccount', on_delete=models.CASCADE,
                                       related_name='revenue_logs', db_index=True)
    parent_transaction = models.ForeignKey('WalletTransaction', on_delete=models.CASCADE,
                                           related_name='revenue_logs', db_index=True)
    revenue_type = models.CharField(max_length=20, choices=RevenueType.choices, db_index=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    original_amount = models.DecimalField(max_digits=18, decimal_places=2,
                                          help_text="Original transaction amount before charge")
    charge_rate = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True,
                                      help_text="Rate used to calculate charge (e.g., 0.01 for 1%)")
    reference = models.CharField(max_length=100, db_index=True)
    description = models.CharField(max_length=255)
    metadata = models.JSONField(default=dict, blank=True)

    objects = RevenueLogManager()

    class Meta:
        verbose_name = "Revenue Log"
        verbose_name_plural = "Revenue Logs"
        ordering = ['-id']
        indexes = [
            models.Index(fields=['wallet_account', '-id']),
            models.Index(fields=['parent_transaction', '-id']),
            models.Index(fields=['revenue_type', '-id']),
            models.Index(fields=['date_created']),
            models.Index(fields=['reference']),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(amount__gte=0), name='positive_revenue_amount'),
            models.CheckConstraint(check=models.Q(original_amount__gte=0), name='positive_original_amount'),
        ]

    def __str__(self):
        return f" {self.amount} - {self.reference}"

    @property
    def total_revenue_generated(self):
        """
        Calculate total revenue generated for this wallet account.
        """
        total = self.wallet_account.revenue_logs.aggregate(
            Sum("amount")
        )["amount__sum"] or Decimal("0.00")
        return total

    def formatted_total_revenue(self):
        """
        Nicely formatted total revenue in HTML.
        """
        amount = self.total_revenue_generated
        if not isinstance(amount, Decimal):
            try:
                amount = Decimal(str(amount))
            except Exception:
                amount = Decimal("0.00")
        formatted_amount = f"KES {amount:,.2f}"
        return format_html("<strong>{}</strong>", formatted_amount)
    formatted_total_revenue.short_description = "Total Revenue Generated"

CHARGE_TIERS = [
    (10000, 20000, Decimal('0.031')),  # 3.1% for 10,001 - 20,000
    (20000, 30000, Decimal('0.032')),  # 3.2% for 20,001 - 30,000
    (30000, 40000, Decimal('0.033')),  # 3.3% for 30,001 - 40,000
    (40000, 50000, Decimal('0.034')),  # 3.4% for 40,001 - 50,000
    (50000, 60000, Decimal('0.035')),  # 3.5% for 50,001 - 60,000
    (60000, 70000, Decimal('0.036')),  # 3.6% for 60,001 - 70,000
    (70000, 80000, Decimal('0.037')),  # 3.7% for 70,001 - 80,000
    (80000, 90000, Decimal('0.038')),  # 3.8% for 80,001 - 90,000
    (90000, 100000, Decimal('0.039')),  # 3.9% for 90,001 - 100,000
    (100000, 110000, Decimal('0.04')),  # 4% for 100,001 - 110,000
    (110000, 120000, Decimal('0.041')),  # 4.1% for 110,001 - 120,000
    (120000, 130000, Decimal('0.042')),  # 4.2% for 120,001 - 130,000
    (130000, 140000, Decimal('0.043')),  # 4.3% for 130,001 - 140,000
    (140000, 150000, Decimal('0.044')),  # 4.4% for 140,001 - 150,000
    (150000, 250000, Decimal('0.045')),  # 4.5% for 150,001 - 250,000
]


def calculate_fair_tiered_charge(amount_kes: float) -> float:
    """Calculate charge with decimal precision and show breakdown"""
    amount = Decimal(str(amount_kes))
    charge_decimal = Decimal('0.0')
    breakdown = []
    if amount <= 10000:
        charge = (amount * Decimal('0.03')).quantize(Decimal('0.01'), rounding=ROUND_UP)
        breakdown.append(f"0 - 10,000 KES: 3% charge = {charge} KES")
    else:
        charge_decimal += Decimal('10000') * Decimal('0.03')
        breakdown.append(f"0 - 10,000 KES: 3% charge = {charge_decimal} KES")
        for lower, upper, rate in CHARGE_TIERS:
            if amount > lower:
                applicable_amount = min(amount, Decimal(str(upper))) - Decimal(str(lower))
                tier_charge = applicable_amount * rate
                charge_decimal += tier_charge
                breakdown.append(f"{lower + 1:,} - {upper:,} KES: {rate * 100}% charge = {tier_charge:.2f} KES")

        charge = float(charge_decimal.quantize(Decimal('0.01'), rounding=ROUND_UP))
    breakdown.append(f"Total Charge: {charge} KES")
    print(breakdown)
    return charge

def get_charge_rate_for_amount(amount: Decimal) -> Decimal:
    """Get the effective charge rate for a given amount (for logging purposes)"""
    if amount <= 0:
        return Decimal('0.0')

    charge = Decimal(str(calculate_fair_tiered_charge(float(amount))))
    return (charge / amount).quantize(Decimal('0.0001'))


class WorkflowActionLog(BaseModel):
    """
    Logs each individual balance movement in the wallet workflow.
    Each topup/payment operation creates multiple action log entries.
    """
    wallet_account = models.ForeignKey('WalletAccount', on_delete=models.CASCADE,
                                       related_name='workflow_actions', db_index=True)
    parent_transaction = models.ForeignKey('WalletTransaction', on_delete=models.CASCADE,
                                           related_name='workflow_actions', db_index=True)
    action_type = models.CharField(max_length=30, choices=WorkflowActionType.choices, db_index=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    balance_type_before = models.DecimalField(max_digits=18, decimal_places=2)
    balance_type_after = models.DecimalField(max_digits=18, decimal_places=2)
    workflow_step = models.CharField(max_length=50)  # e.g., 'initiate_topup', 'payment_approved'
    sequence_order = models.PositiveSmallIntegerField()  # Order of actions within a transaction
    reference = models.CharField(max_length=100, db_index=True)
    description = models.CharField(max_length=255)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Workflow Action Log"
        verbose_name_plural = "Workflow Action Logs"
        ordering = ['-id']
        indexes = [
            models.Index(fields=['wallet_account', '-id']),
            models.Index(fields=['parent_transaction', 'sequence_order']),
            models.Index(fields=['action_type', '-id']),
            models.Index(fields=['workflow_step', '-id']),
            models.Index(fields=['reference']),
            models.Index(fields=['date_created']),
        ]

    def __str__(self):
        return f"{self.parent_transaction.transaction_type.replace('_', ' ').title()} - {self.amount} - {self.reference} ({self.parent_transaction.status})"


def disable_for_loaddata(signal_handler):
    """Decorator to disable signal handlers during fixture loading."""

    def wrapper(*args, **kwargs):
        if kwargs.get('raw'):
            return
        signal_handler(*args, **kwargs)

    return wrapper


@receiver(post_save, sender=Contribution)
@disable_for_loaddata
def create_wallet_account_for_contribution(sender, instance, created, **kwargs):
    """Auto-create wallet account when contribution is created."""
    if created:
        try:
            with transaction.atomic():
                account_number = WalletAccount.generate_next_account_number()
                WalletAccount.objects.create(
                    contribution=instance,
                    account_number=account_number,
                    currency=getattr(instance, 'currency', 'KES'),
                    is_active=True
                )
                logger.info(f"Created wallet account {account_number} for contribution {instance.id}")
        except Exception as e:
            logger.error(f"Failed to create wallet account for contribution {instance.id}: {str(e)}")
            raise ValidationError(
                f"Failed to create wallet account for contribution {instance.id}: {str(e)}"
            ) # from e.get_action_type_display()} - "{self.amount} - {self.workflow_step}"


class WalletAccountManager(models.Manager):
    """Custom manager for WalletAccount with useful query methods."""

    def active(self):
        """Get only active wallet accounts."""
        return self.filter(is_active=True)

    def with_balance(self):
        """Get accounts that have some balance."""
        return self.filter(current__gt=0)

    def by_contribution(self, contribution):
        """Get wallet accounts for a specific contribution."""
        return self.filter(contribution=contribution)

    def get_balance_summary(self) -> Dict:
        """Get aggregated balance summary across all active accounts."""
        return self.active().aggregate(
            total_current=models.Sum('current'),
            total_available=models.Sum('available'),
            total_reserved=models.Sum('reserved'),
            total_uncleared=models.Sum('uncleared')
        )


class WalletAccount(BaseModel):
    """
    Wallet account model optimized for billing workflow with comprehensive action logging.

    Balance Flow:
    1. TopUp: current += amount, uncleared += amount (Transaction: pending)
    2. TopUp Approved: uncleared -= amount, available += amount (Transaction: completed)
    3. TopUp Rejected: current -= amount, uncleared -= amount (Transaction: failed)
    4. Payment: available -= amount, reserved += amount (Transaction: pending)
    5. Payment Approved: reserved -= amount, current -= amount (Transaction: completed)
    6. Payment Rejected: reserved -= amount, available += amount (Transaction: failed)
    """
    contribution = models.ForeignKey(Contribution, on_delete=models.CASCADE,
                                     related_name='wallet_accounts', db_index=True)
    account_number = models.CharField(max_length=20, unique=True, db_index=True)
    current = models.DecimalField(max_digits=18, decimal_places=2,
                                          default=Decimal('0.00'), db_index=True)
    available = models.DecimalField(max_digits=18, decimal_places=2,
                                            default=Decimal('0.00'))
    reserved = models.DecimalField(max_digits=18, decimal_places=2,
                                           default=Decimal('0.00'))
    uncleared = models.DecimalField(max_digits=18, decimal_places=2,
                                            default=Decimal('0.00'))
    is_active = models.BooleanField(default=True, db_index=True)
    is_frozen = models.BooleanField(default=False, db_index=True)
    currency = models.CharField(max_length=3, default='KES', db_index=True)
    version = models.PositiveIntegerField(default=1)
    last_transaction_date = models.DateTimeField(null=True, blank=True, db_index=True)
    state = models.ForeignKey(State, on_delete=models.CASCADE, null=True, blank=True)

    objects = WalletAccountManager()

    class Meta:
        verbose_name = "Wallet Account"
        verbose_name_plural = "Wallet Accounts"
        ordering = ['-id']
        indexes = [
            models.Index(fields=['contribution', 'is_active']),
            models.Index(fields=['account_number']),
            models.Index(fields=['current', 'is_active']),
            models.Index(fields=['currency', 'is_active']),
            models.Index(fields=['last_transaction_date']),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(current__gte=0),
                                   name='positive_current'),
            models.CheckConstraint(check=models.Q(available__gte=0),
                                   name='positive_available'),
            models.CheckConstraint(check=models.Q(reserved__gte=0),
                                   name='positive_reserved'),
            models.CheckConstraint(check=models.Q(uncleared__gte=0),
                                   name='positive_uncleared'),
        ]

    def __str__(self):
        return f"{self.account_number} - {self.currency} {self.current}"

    def clean(self):
        """Validate balance relationships according to workflow."""
        super().clean()
        calculated_current = self.available + self.reserved + self.uncleared
        if abs(self.current - calculated_current) > Decimal('0.01'):
            raise ValidationError(
                f"Balance mismatch: current={self.current}, "
                f"calculated={calculated_current} (available={self.available} + "
                f"reserved={self.reserved} + uncleared={self.uncleared})"
            )

    def save(self, *args, **kwargs):
        """Override save to increment version and validate."""
        if self.pk:
            self.version += 1
        self.full_clean()
        super().save(*args, **kwargs)

    def _log_workflow_actions(self, transaction_obj: 'WalletTransaction', actions: List[Dict]):
        """Helper method to log multiple workflow actions for a transaction."""
        workflow_actions = []
        max_sequence = WorkflowActionLog.objects.filter(
            parent_transaction=transaction_obj
        ).aggregate(max_seq=models.Max('sequence_order'))['max_seq'] or 0

        for i, action in enumerate(actions, max_sequence + 1):
            workflow_action = WorkflowActionLog(
                wallet_account=self,
                parent_transaction=transaction_obj,
                action_type=action['action_type'],
                amount=action['amount'],
                balance_type_before=action['balance_before'],
                balance_type_after=action['balance_after'],
                workflow_step=action['workflow_step'],
                sequence_order=i,
                reference=transaction_obj.reference,
                description=action['description'],
                metadata=action.get('metadata', {})
            )
            workflow_actions.append(workflow_action)
        WorkflowActionLog.objects.bulk_create(workflow_actions)

    def _log_revenue(self, transaction_obj, revenue_type, amount, original_amount, description, metadata=None):
        """Helper method to log revenue from charges."""
        charge_rate = get_charge_rate_for_amount(original_amount) if original_amount > 0 else Decimal('0.0')

        RevenueLog.objects.create(
            wallet_account=self,
            parent_transaction=transaction_obj,
            revenue_type=revenue_type,
            amount=amount,
            original_amount=original_amount,
            charge_rate=charge_rate,
            reference=transaction_obj.reference,
            description=description,
            metadata=metadata or {}
        )
        logger.info(f"Revenue logged: {amount} from {revenue_type} for transaction {transaction_obj.reference}")

    @transaction.atomic
    def initiate_topup(self, amount, reference, charge , receipt, amount_plus_charge, actioned_by, description="TopUp - Pending"):
        """
        Step 1: TopUp - Add money to current and uncleared (pending approval).
        Creates new transaction with status 'pending'
        Logs: money_to_current, money_to_uncleared
        """
        if amount <= 0:
            raise ValidationError("TopUp amount must be positive")
        state = State.objects.get(name='Pending')
        account = WalletAccount.objects.select_for_update().get(pk=self.pk)
        amount = Decimal(str(amount))
        old_current = account.current
        old_uncleared = account.uncleared
        account.current += amount
        account.uncleared += amount
        account.last_transaction_date = timezone.now()
        account.save()

        transaction_obj = WalletTransaction.objects.create(
            wallet_account=account,
            transaction_type='topup',
            amount=amount,
            balance_before=old_current,
            balance_after=account.current,
            reference=reference,
            receipt_number=receipt,
            amount_plus_charge=amount_plus_charge,
            charge=charge,
            description=description,
            actioned_by=actioned_by,
            status=state,
            metadata={
                'workflow_step': 'initiate_topup',
                'uncleared_before': str(old_uncleared),
                'uncleared_after': str(account.uncleared),
            }
        )

        actions = [
            {
                'action_type': WorkflowActionType.MONEY_TO_CURRENT,
                'amount': amount,
                'balance_before': old_current,
                'balance_after': account.current,
                'workflow_step': 'initiate_topup',
                'description': f'Added {amount} to current balance',
            },
            {
                'action_type': WorkflowActionType.MONEY_TO_UNCLEARED,
                'amount': amount,
                'balance_before': old_uncleared,
                'balance_after': account.uncleared,
                'workflow_step': 'initiate_topup',
                'description': f'Added {amount} to uncleared balance',
            }
        ]

        self._log_workflow_actions(transaction_obj, actions)
        logger.info(f"TopUp pending: {amount} added to account {self.account_number}")
        if charge > 0:
            self._log_revenue(
                transaction_obj=transaction_obj,
                revenue_type=RevenueType.TOPUP_CHARGE,
                amount=charge,
                original_amount=amount_plus_charge,
                description=f'TopUp charge for {amount_plus_charge}',
                metadata={
                    'status': 'pending',
                    'mpesa_reference': receipt,
                    'total_received': str(amount_plus_charge)
                }
            )
        return transaction_obj

    @transaction.atomic
    def topup_approved(self, amount, reference, description="TopUp - Approved", receipt=""):
        """
        Step 2: TopUp Approved - Move money from uncleared to available.
        Updates existing transaction to 'completed' status
        Logs: money_from_uncleared, money_to_available
        """
        if amount <= 0:
            raise ValidationError("Approval amount must be positive")

        account = WalletAccount.objects.select_for_update().get(pk=self.pk)
        amount = Decimal(str(amount))
        state_pending = State.objects.get(name='Pending')
        completed = State.objects.get(name='Completed')
        if account.uncleared < amount:
            raise ValidationError(f"Cannot approve {amount}. Uncleared balance: {account.uncleared}")
        try:
            transaction_obj = WalletTransaction.objects.get(
                wallet_account=account,
                reference=reference,
                transaction_type='topup',
                status=state_pending
            )
        except WalletTransaction.DoesNotExist:
            raise ValidationError(f"No pending topup transaction found for reference: {reference}")
        old_uncleared = account.uncleared
        old_available = account.available
        account.uncleared -= amount
        account.available += amount
        account.last_transaction_date = timezone.now()
        account.save()
        transaction_obj.status = completed
        transaction_obj.receipt_number = receipt
        transaction_obj.description = description
        transaction_obj.metadata.update({
            'workflow_step': 'topup_approved',
            'approved_at': timezone.now().isoformat(),
            'uncleared_before_approval': str(old_uncleared),
            'uncleared_after_approval': str(account.uncleared),
            'available_before_approval': str(old_available),
            'available_after_approval': str(account.available),
        })
        transaction_obj.save()

        actions = [
            {
                'action_type': WorkflowActionType.MONEY_FROM_UNCLEARED,
                'amount': amount,
                'balance_before': old_uncleared,
                'balance_after': account.uncleared,
                'workflow_step': 'topup_approved',
                'description': f'Deducted {amount} from uncleared balance',
            },
            {
                'action_type': WorkflowActionType.MONEY_TO_AVAILABLE,
                'amount': amount,
                'balance_before': old_available,
                'balance_after': account.available,
                'workflow_step': 'topup_approved',
                'description': f'Added {amount} to available balance',
            }
        ]

        self._log_workflow_actions(transaction_obj, actions)
        logger.info(f"TopUp approved: {amount} moved to available in account {self.account_number}")
        try:
            revenue_logs = RevenueLog.objects.filter(
                parent_transaction=transaction_obj,
                revenue_type=RevenueType.TOPUP_CHARGE
            )
            for revenue_log in revenue_logs:
                revenue_log.metadata.update({
                    'status': 'realized',
                    'approved_at': timezone.now().isoformat()
                })
                revenue_log.save()
        except RevenueLog.DoesNotExist:
            pass  # No charge was applied
        return transaction_obj

    @transaction.atomic
    def topup_rejected(self, amount, reference, description="TopUp - Rejected"):
        """
        TopUp Rejected - Reverse the pending topup.
        Updates existing transaction to 'failed' status
        Logs: money_from_current, money_from_uncleared
        """
        if amount <= 0:
            raise ValidationError("Rejection amount must be positive")
        state_pending = State.objects.get(name='Pending')
        failed = State.objects.get(name='Failed')
        account = WalletAccount.objects.select_for_update().get(pk=self.pk)
        amount = Decimal(str(amount))
        try:
            transaction_obj = WalletTransaction.objects.get(
                wallet_account=account,
                reference=reference,
                transaction_type='topup',
                status=state_pending
            )
        except WalletTransaction.DoesNotExist:
            raise ValidationError(f"No pending topup transaction found for reference: {reference}")

        if account.uncleared < amount:
            raise ValidationError(f"Cannot reject {amount}. Uncleared balance: {account.uncleared}")

        if account.current < amount:
            raise ValidationError(f"Cannot reject {amount}. Current balance: {account.current}")

        old_current = account.current
        old_uncleared = account.uncleared

        account.current -= amount
        account.uncleared -= amount
        account.last_transaction_date = timezone.now()
        account.save()
        transaction_obj.status = failed
        transaction_obj.description = description
        transaction_obj.balance_after = account.current
        transaction_obj.metadata.update({
            'workflow_step': 'topup_rejected',
            'rejected_at': timezone.now().isoformat(),
            'rejection_reason': description,
            'uncleared_before_rejection': str(old_uncleared),
            'uncleared_after_rejection': str(account.uncleared),
        })
        transaction_obj.save()

        actions = [
            {
                'action_type': WorkflowActionType.MONEY_FROM_CURRENT,
                'amount': amount,
                'balance_before': old_current,
                'balance_after': account.current,
                'workflow_step': 'topup_rejected',
                'description': f'Deducted {amount} from current balance',
            },
            {
                'action_type': WorkflowActionType.MONEY_FROM_UNCLEARED,
                'amount': amount,
                'balance_before': old_uncleared,
                'balance_after': account.uncleared,
                'workflow_step': 'topup_rejected',
                'description': f'Deducted {amount} from uncleared balance',
            }
        ]

        self._log_workflow_actions(transaction_obj, actions)
        logger.info(f"TopUp rejected: {amount} removed from account {self.account_number}")
        try:
            revenue_logs = RevenueLog.objects.filter(
                parent_transaction=transaction_obj,
                revenue_type=RevenueType.TOPUP_CHARGE
            )
            for revenue_log in revenue_logs:
                revenue_log.metadata.update({
                    'status': 'unrealized',
                    'rejected_at': timezone.now().isoformat(),
                    'rejection_reason': description
                })
                revenue_log.save()
        except RevenueLog.DoesNotExist:
            pass
        return transaction_obj

    @transaction.atomic
    def initiate_payment(self, amount, reference, charge, receipt, amount_plus_charge, actioned_by,description="Payment - Pending", ):
        """
        Step 3: Payment - Move money from available to reserved.
        Creates new transaction with status 'pending'
        Logs: money_from_available, money_to_reserved
        """
        if amount <= 0:
            raise ValidationError("Payment amount must be positive")
        account = WalletAccount.objects.select_for_update().get(pk=self.pk)
        if account.is_frozen:
            raise ValidationError("Account is frozen")
        state = State.objects.get(name='Pending')
        amount = Decimal(str(amount))

        if account.available < amount:
            raise ValidationError(f"Insufficient available balance. Available: {account.available}")
        amount = amount + charge
        old_available = account.available
        old_reserved = account.reserved
        account.available -= amount
        account.reserved += amount
        account.last_transaction_date = timezone.now()
        account.save()
        transaction_obj = WalletTransaction.objects.create(
            wallet_account=account,
            transaction_type='payment',
            amount=amount,
            balance_before=account.current,
            balance_after=account.current,
            reference=reference,
            description=description,
            amount_plus_charge=amount_plus_charge,
            charge=charge,
            actioned_by=actioned_by,
            receipt_number=receipt,
            status=state,
            metadata={
                'workflow_step': 'initiate_payment',
                'available_before': str(old_available),
                'available_after': str(account.available),
                'reserved_before': str(old_reserved),
                'reserved_after': str(account.reserved),
            }
        )

        actions = [
            {
                'action_type': WorkflowActionType.MONEY_FROM_AVAILABLE,
                'amount': amount,
                'balance_before': old_available,
                'balance_after': account.available,
                'workflow_step': 'initiate_payment',
                'description': f'Deducted {amount} from available balance',
            },
            {
                'action_type': WorkflowActionType.MONEY_TO_RESERVED,
                'amount': amount,
                'balance_before': old_reserved,
                'balance_after': account.reserved,
                'workflow_step': 'initiate_payment',
                'description': f'Added {amount} to reserved balance',
            }
        ]

        self._log_workflow_actions(transaction_obj, actions)
        logger.info(f"Payment pending: {amount} reserved in account {self.account_number}")
        return transaction_obj



    @transaction.atomic
    def payment_approved(self, amount, reference, description="Payment - Approved", receipt=""):
        """
        Step 4: Payment Approved - Remove money from reserved and current.
        Updates existing transaction to 'completed' status
        Logs: money_from_reserved, money_from_current
        """
        if amount <= 0:
            raise ValidationError("Approval amount must be positive")

        account = WalletAccount.objects.select_for_update().get(pk=self.pk)
        amount = Decimal(str(amount))
        state_pending = State.objects.get(name='Pending')
        state_completed = State.objects.get(name='Completed')
        try:
            transaction_obj = WalletTransaction.objects.get(
                wallet_account=account,
                reference=reference,
                transaction_type='payment',
                status=state_pending
            )
        except WalletTransaction.DoesNotExist:
            raise ValidationError(f"No pending payment transaction found for reference: {reference}")
        charge = transaction_obj.charge or Decimal('0.00')
        amount = amount + charge
        if account.reserved < amount:
            raise ValidationError(f"Cannot approve {amount}. Reserved balance: {account.reserved}")

        if account.current < amount:
            raise ValidationError(f"Cannot approve {amount}. Current balance: {account.current}")

        old_current = account.current
        old_reserved = account.reserved
        account.reserved -= amount
        account.current -= amount
        account.last_transaction_date = timezone.now()
        account.save()
        transaction_obj.status = state_completed
        transaction_obj.description = description
        transaction_obj.receipt_number = receipt
        transaction_obj.balance_after = account.current
        transaction_obj.metadata.update({
            'workflow_step': 'payment_approved',
            'approved_at': timezone.now().isoformat(),
            'reserved_before_approval': str(old_reserved),
            'reserved_after_approval': str(account.reserved),
            'current_before_approval': str(old_current),
            'current_after_approval': str(account.current),
        })
        transaction_obj.save()
        actions = [
            {
                'action_type': WorkflowActionType.MONEY_FROM_RESERVED,
                'amount': amount,
                'balance_before': old_reserved,
                'balance_after': account.reserved,
                'workflow_step': 'payment_approved',
                'description': f'Deducted {amount} from reserved balance',
            },
            {
                'action_type': WorkflowActionType.MONEY_FROM_CURRENT,
                'amount': amount,
                'balance_before': old_current,
                'balance_after': account.current,
                'workflow_step': 'payment_approved',
                'description': f'Deducted {amount} from current balance',
            }
        ]

        self._log_workflow_actions(transaction_obj, actions)
        logger.info(f"Payment approved: {amount} deducted from account {self.account_number}")
        return transaction_obj

    @transaction.atomic
    def payment_rejected(self, amount, reference, description="Payment - Rejected"):
        """
        Payment Rejected - Move money back from reserved to available.
        Updates existing transaction to 'failed' status
        Logs: money_from_reserved, money_to_available
        """
        if amount <= 0:
            raise ValidationError("Rejection amount must be positive")
        state_pending = State.objects.get(name='Pending')
        failed = State.objects.get(name='Failed')
        account = WalletAccount.objects.select_for_update().get(pk=self.pk)
        amount = Decimal(str(amount))
        try:
            transaction_obj = WalletTransaction.objects.get(
                wallet_account=account,
                reference=reference,
                transaction_type='payment',
                status=state_pending
            )
        except WalletTransaction.DoesNotExist:
            raise ValidationError(f"No pending payment transaction found for reference: {reference}")

        if account.reserved < amount:
            raise ValidationError(f"Cannot reject {amount}. Reserved balance: {account.reserved}")

        old_available = account.available
        old_reserved = account.reserved

        account.reserved -= amount
        account.available += amount
        account.last_transaction_date = timezone.now()
        account.save()
        transaction_obj.status = failed
        transaction_obj.description = description
        transaction_obj.metadata.update({
            'workflow_step': 'payment_rejected',
            'rejected_at': timezone.now().isoformat(),
            'rejection_reason': description,
            'available_before_rejection': str(old_available),
            'available_after_rejection': str(account.available),
            'reserved_before_rejection': str(old_reserved),
            'reserved_after_rejection': str(account.reserved),
        })
        transaction_obj.save()

        actions = [
            {
                'action_type': WorkflowActionType.MONEY_FROM_RESERVED,
                'amount': amount,
                'balance_before': old_reserved,
                'balance_after': account.reserved,
                'workflow_step': 'payment_rejected',
                'description': f'Deducted {amount} from reserved balance',
            },
            {
                'action_type': WorkflowActionType.MONEY_TO_AVAILABLE,
                'amount': amount,
                'balance_before': old_available,
                'balance_after': account.available,
                'workflow_step': 'payment_rejected',
                'description': f'Added {amount} to available balance',
            }
        ]

        self._log_workflow_actions(transaction_obj, actions)
        logger.info(f"Payment rejected: {amount} returned to available in account {self.account_number}")
        self._log_workflow_actions(transaction_obj, actions)

        charge = transaction_obj.charge or Decimal('0.00')
        total_amount = amount + charge
        return transaction_obj

    def freeze_account(self):
        """Freeze the account."""
        self.is_frozen = True
        self.save(update_fields=['is_frozen', 'version'])

    def unfreeze_account(self):
        """Unfreeze the account."""
        self.is_frozen = False
        self.save(update_fields=['is_frozen', 'version'])

    @classmethod
    def generate_next_account_number(cls, prefix="1", length=12):
        """Generate next sequential account number with proper locking."""
        with transaction.atomic():
            latest_account = cls.objects.select_for_update().filter(
                account_number__regex=r'^\d+$'
            ).order_by('-account_number').first()

            if latest_account and latest_account.account_number.isdigit():
                try:
                    next_number = int(latest_account.account_number) + 1
                except (ValueError, TypeError):
                    next_number = int(prefix + "0" * (length - len(prefix) - 1) + "1")
            else:
                next_number = int(prefix + "0" * (length - len(prefix) - 1) + "1")

            account_number = str(next_number).zfill(length)
            while cls.objects.filter(account_number=account_number).exists():
                next_number += 1
                account_number = str(next_number).zfill(length)

            return account_number

    @property
    def balance_summary(self):
        """Get complete balance breakdown."""
        return {
            'current': self.current,
            'available': self.available,
            'reserved': self.reserved,
            'uncleared': self.uncleared,
            'currency': self.currency,
            'is_frozen': self.is_frozen,
            'account_number': self.account_number
        }

    def get_workflow_actions(self, limit: Optional[int] = None):
        """Get workflow actions for this account."""
        queryset = self.workflow_actions.select_related('parent_transaction').order_by('-id')
        if limit:
            queryset = queryset[:limit]
        return queryset


class WalletTransactionManager(models.Manager):
    """Custom manager for WalletTransaction."""

    def by_type(self, transaction_type):
        """Filter by transaction type."""
        return self.filter(transaction_type=transaction_type)

    def pending(self):
        """Get pending transactions."""
        return self.filter(status='pending')

    def completed(self):
        """Get completed transactions."""
        return self.filter(status='completed')


class WalletTransaction(BaseModel):
    """
    Transaction history optimized for billing workflow.
    Each transaction represents a complete workflow (topup or payment).
    Status changes from 'pending' to 'completed'/'failed' based on approval/rejection.
    """

    TRANSACTION_TYPES = [
        ('topup', 'TopUp'),
        ('payment', 'Payment'),
        ('withdrawal', 'Withdrawal'),
        ('adjustment', 'Manual Adjustment'),
        ('refund', 'Refund'),
    ]

    wallet_account = models.ForeignKey(WalletAccount, on_delete=models.CASCADE, related_name='transactions', db_index=True)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES, db_index=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    amount_plus_charge = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal())
    balance_before = models.DecimalField(max_digits=18, decimal_places=2)
    balance_after = models.DecimalField(max_digits=18, decimal_places=2)
    charge = models.DecimalField(max_digits=18, decimal_places=2, db_index=True, null=True, blank=True)
    actioned_by = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, db_index=True)
    reference = models.CharField(max_length=100, unique=True, db_index=True)
    receipt_number = models.CharField(max_length=100, db_index=True)
    description = models.CharField(max_length=255, blank=True)
    status = models.ForeignKey(State, on_delete=models.CASCADE, null=True, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    objects = WalletTransactionManager()

    class Meta:
        verbose_name = "Wallet Transaction"
        verbose_name_plural = "Wallet Transactions"
        ordering = ['-id']
        indexes = [
            models.Index(fields=['wallet_account', '-id']),
            models.Index(fields=['transaction_type', '-id']),
            models.Index(fields=['reference']),
            models.Index(fields=['status', '-id']),
            models.Index(fields=['date_created']),
            models.Index(fields=['wallet_account', 'transaction_type', '-id']),
        ]

    def __str__(self):
        return f"{self.transaction_type} - {self.amount} - {self.reference} ({self.status})"


class BalanceLog(BaseModel):
    """BalanceLog Model. This model defines the actual execution carried out by a rule profile execution."""
    transaction = models.ForeignKey(WalletTransaction, on_delete=models.CASCADE)
    balance_entry_type = models.ForeignKey(BalanceEntryType, on_delete=models.CASCADE)
    reference = models.CharField(max_length=100, null=True, blank=True)
    receipt = models.CharField(max_length=100, null=True, blank=True)
    amount_transacted = models.DecimalField(max_digits=25, decimal_places=2, default=0.00)
    total_balance = models.DecimalField(max_digits=25, decimal_places=2, default=0.00)
    description = models.TextField(null=True, blank=True)
    state = models.ForeignKey(State, on_delete=models.CASCADE)

    def __str__(self):
        return '%s %s : %s' % (self.transaction, self.balance_entry_type, self.amount_transacted)

    class Meta(BaseModel.Meta):
        ordering = ('-date_created',)
        verbose_name = "Balance Log"
        verbose_name_plural = 'Balance Logs'


class BalanceLogEntry(BaseModel):
    """An entry that affects the balances on the respective account. e.g. Payment - Dr - Available - Active"""
    process_log = models.ForeignKey(BalanceLog, on_delete=models.CASCADE)
    entry_type = models.ForeignKey(EntryType, on_delete=models.CASCADE)
    account_field_type = models.ForeignKey(AccountFieldType, on_delete=models.CASCADE)
    amount_transacted = models.DecimalField(max_digits=25, decimal_places=2, default=0.00)
    state = models.ForeignKey(State, on_delete=models.CASCADE)

    def __str__(self):
        return '%s %s %s' % (self.process_log, self.account_field_type, self.amount_transacted)

    class Meta(object):
        """Meta Class"""
        verbose_name = "Balance Log Entry"
        verbose_name_plural = "Balance Logs Entries"


class Pledge(BaseModel):
    pledger_name = models.CharField(max_length=255, help_text="Person/Organization making the pledge")
    pledger_contact = models.CharField(max_length=100, blank=True, null=True, help_text="Phone/email of the pledger")
    contribution = models.ForeignKey(Contribution, null=True, blank=True, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    purpose = models.TextField(blank=True, null=True, help_text="What is this pledge for?")
    planned_clear_date = models.DateField(blank=True, null=True, help_text="When the pledger intends to clear the pledge")
    status = models.ForeignKey(State, on_delete=models.CASCADE)
    raised_by = models.CharField(max_length=100, blank=True, null=True, help_text="User who raised this pledge")

    def __str__(self):
        return f"{self.pledger_name} - {self.amount} ({self.status.name})"

    @property
    def total_paid(self) -> Decimal:
        """Total amount paid towards this pledge."""
        return self.logs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    @property
    def balance(self) -> Decimal:
        """Remaining balance on this pledge."""
        return self.amount - self.total_paid

    def add_payment(self, amount: Decimal, user=None, note=""):
        """
        Add a payment (PledgeLog), auto-calculates new balance & updates status.
        """
        log = PledgeLog.objects.create(
            pledge=self,
            amount=amount,
            balance=self.balance - amount,
            note=note,
            logged_by=user,
        )
        self._update_status()
        return log

    def _update_status(self):
        """
        Update pledge status based on payments made.
        Requires `State` table to have: Pending, Partially Paid, Cleared.
        """
        paid = self.total_paid

        if paid <= 0:
            state_name = "Pending"
        elif paid < self.amount:
            state_name = "Partially Paid"
        else:
            state_name = "Cleared"

        try:
            new_state = State.objects.get(name=state_name)
            if self.status_id != new_state.id:
                self.status = new_state
                self.save(update_fields=["status", "date_modified"])
        except State.DoesNotExist:
            pass


class PledgeLog(BaseModel):
    pledge = models.ForeignKey(
        Pledge,
        on_delete=models.CASCADE,
        related_name="logs"
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Payment amount recorded"
    )
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Remaining pledge balance after this payment",
        default=0
    )
    note = models.TextField(blank=True, null=True, help_text="Optional note about this payment")

    logged_by = models.CharField(max_length=100, blank=True, null=True, help_text="User who logged this pledge")

    class Meta:
        ordering = ["-date_created"]

    def __str__(self):
        return f"{self.pledge.pledger_name} paid {self.amount}, balance {self.balance} on {self.date_created:%Y-%m-%d}"

    def save(self, *args, **kwargs):
        """
        Ensure balance is set correctly before saving.
        """
        if not self.pk and not self.balance:
            already_paid = self.pledge.total_paid
            new_total = already_paid + self.amount
            self.balance = self.pledge.amount - new_total
        super().save(*args, **kwargs)
