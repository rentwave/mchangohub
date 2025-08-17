from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from decimal import Decimal
import logging
from typing import Dict, List, Optional
from enum import Enum
from base.models import BaseModel, State, EntryType, AccountFieldType, BalanceEntryType
from billing.helpers.generate_unique_ref import TransactionRefGenerator
from contributions.models import Contribution

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
	
	@transaction.atomic
	def initiate_topup(self, amount, reference, charge , receipt, description="TopUp - Pending"):
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
			charge=charge,
			description=description,
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
		return transaction_obj
	
	@transaction.atomic
	def initiate_payment(self, amount, reference, charge, receipt, description="Payment - Pending"):
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
			charge=charge,
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
		('adjustment', 'Manual Adjustment'),
		('refund', 'Refund'),
	]
	
	wallet_account = models.ForeignKey(WalletAccount, on_delete=models.CASCADE, related_name='transactions', db_index=True)
	transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES, db_index=True)
	amount = models.DecimalField(max_digits=18, decimal_places=2)
	balance_before = models.DecimalField(max_digits=18, decimal_places=2)
	balance_after = models.DecimalField(max_digits=18, decimal_places=2)
	charge = models.DecimalField(max_digits=18, decimal_places=2, db_index=True, null=True, blank=True)
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
