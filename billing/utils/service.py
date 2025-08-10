"""Utility functions for wallet operations."""

from django.db import transaction
from django.core.exceptions import ValidationError
from decimal import Decimal
from typing import Dict, List, Optional
import uuid

from django.db.models import Count, Sum

from billing.models import WalletAccount, WorkflowActionLog, WalletTransaction


class WalletService:
	"""Service class for wallet operations with comprehensive logging."""
	
	@staticmethod
	def generate_reference(prefix: str = "TXN") -> str:
		"""Generate unique transaction reference."""
		return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"
	
	@staticmethod
	def bulk_topup_pending(accounts_data: List[Dict]) -> List[Dict]:
		"""
		Bulk topup pending for multiple accounts.

		Args:
			accounts_data: List of dicts with keys: account_id, amount, reference, description

		Returns:
			List of results with success/error status
		"""
		results = []
		
		with transaction.atomic():
			for data in accounts_data:
				try:
					account = WalletAccount.objects.get(id=data['account_id'])
					success = account.topup_pending(
						amount=data['amount'],
						reference=data.get('reference', WalletService.generate_reference("BULK-TOPUP")),
						description=data.get('description', "Bulk TopUp - Pending")
					)
					results.append({
						'account_id': data['account_id'],
						'account_number': account.account_number,
						'success': success,
						'amount': data['amount']
					})
				except Exception as e:
					results.append({
						'account_id': data['account_id'],
						'success': False,
						'error': str(e),
						'amount': data['amount']
					})
		
		return results
	
	@staticmethod
	def get_account_workflow_summary(account_id: int, days: int = 30) -> Dict:
		"""
		Get workflow action summary for an account over specified days.

		Args:
			account_id: Wallet account ID
			days: Number of days to look back

		Returns:
			Dictionary with workflow statistics
		"""
		from django.utils import timezone
		from datetime import timedelta
		
		cutoff_date = timezone.now() - timedelta(days=days)
		
		actions = WorkflowActionLog.objects.filter(
			wallet_account_id=account_id,
			date_created__gte=cutoff_date
		).values('action_type').annotate(
			count=Count('id'),
			total_amount=Sum('amount')
		)
		
		transactions = WalletTransaction.objects.filter(
			wallet_account_id=account_id,
			date_created__gte=cutoff_date
		).values('transaction_type').annotate(
			count=Count('id'),
			total_amount=Sum('amount')
		)
		
		return {
			'period_days': days,
			'workflow_actions': list(actions),
			'transactions': list(transactions),
			'cutoff_date': cutoff_date
		}
	
	@staticmethod
	def reconcile_account_balance(account_id: int) -> Dict:
		"""
		Reconcile account balance by checking all workflow actions.

		Args:
			account_id: Wallet account ID

		Returns:
			Dictionary with reconciliation results
		"""
		account = WalletAccount.objects.get(id=account_id)
		
		# Calculate expected balances from workflow actions
		actions = WorkflowActionLog.objects.filter(
			wallet_account_id=account_id
		).order_by('id')
		
		calculated_balances = {
			'current': Decimal('0.00'),
			'available': Decimal('0.00'),
			'reserved': Decimal('0.00'),
			'uncleared': Decimal('0.00')
		}
		
		for action in actions:
			action_type = action.action_type
			amount = action.amount
			
			if action_type == 'money_to_current':
				calculated_balances['current'] += amount
			elif action_type == 'money_from_current':
				calculated_balances['current'] -= amount
			elif action_type == 'money_to_available':
				calculated_balances['available'] += amount
			elif action_type == 'money_from_available':
				calculated_balances['available'] -= amount
			elif action_type == 'money_to_reserved':
				calculated_balances['reserved'] += amount
			elif action_type == 'money_from_reserved':
				calculated_balances['reserved'] -= amount
			elif action_type == 'money_to_uncleared':
				calculated_balances['uncleared'] += amount
			elif action_type == 'money_from_uncleared':
				calculated_balances['uncleared'] -= amount
		
		# Compare with actual account balances
		actual_balances = {
			'current': account.current_balance,
			'available': account.available_balance,
			'reserved': account.reserved_balance,
			'uncleared': account.uncleared_balance
		}
		
		discrepancies = {}
		for balance_type in calculated_balances:
			diff = actual_balances[balance_type] - calculated_balances[balance_type]
			if abs(diff) > Decimal('0.01'):  # Allow for small rounding differences
				discrepancies[balance_type] = {
					'actual': actual_balances[balance_type],
					'calculated': calculated_balances[balance_type],
					'difference': diff
				}
		
		return {
			'account_number': account.account_number,
			'actual_balances': actual_balances,
			'calculated_balances': calculated_balances,
			'discrepancies': discrepancies,
			'is_balanced': len(discrepancies) == 0,
			'total_actions_processed': actions.count()
		}
	
	@staticmethod
	def get_system_health_report() -> Dict:
		"""
		Generate system-wide health report for wallet operations.

		Returns:
			Dictionary with system health metrics
		"""
		from django.db.models import Sum, Count, Q
		total_accounts = WalletAccount.objects.count()
		active_accounts = WalletAccount.objects.filter(is_active=True).count()
		frozen_accounts = WalletAccount.objects.filter(is_frozen=True).count()
		balance_totals = WalletAccount.objects.aggregate(
			total_current=Sum('current_balance'),
			total_available=Sum('available_balance'),
			total_reserved=Sum('reserved_balance'),
			total_uncleared=Sum('uncleared_balance')
		)
		pending_transactions = WalletTransaction.objects.filter(status='pending').count()
		failed_transactions = WalletTransaction.objects.filter(status='failed').count()
		from django.utils import timezone
		from datetime import timedelta
		
		last_24h = timezone.now() - timedelta(hours=24)
		recent_transactions = WalletTransaction.objects.filter(
			date_created__gte=last_24h
		).count()
		recent_actions = WorkflowActionLog.objects.filter(
			date_created__gte=last_24h
		).count()
		issues = []
		
		if frozen_accounts > 0:
			issues.append(f"{frozen_accounts} accounts are frozen")
		
		if pending_transactions > 100:
			issues.append(f"{pending_transactions} transactions are pending")
		
		if failed_transactions > 0:
			issues.append(f"{failed_transactions} transactions have failed")
		
		balance_integrity = True
		for account in WalletAccount.objects.all():
			try:
				account.clean()
			except ValidationError:
				balance_integrity = False
				issues.append(f"Balance integrity issue in account {account.account_number}")
		
		return {
			'timestamp': timezone.now(),
			'accounts': {
				'total': total_accounts,
				'active': active_accounts,
				'frozen': frozen_accounts,
				'health_score': (active_accounts / total_accounts * 100) if total_accounts > 0 else 100
			},
			'balances': balance_totals,
			'transactions': {
				'pending': pending_transactions,
				'failed': failed_transactions,
				'recent_24h': recent_transactions
			},
			'workflow_actions': {
				'recent_24h': recent_actions
			},
			'balance_integrity': balance_integrity,
			'issues': issues,
			'overall_health': 'Good' if len(issues) == 0 else 'Issues Detected'
		}

