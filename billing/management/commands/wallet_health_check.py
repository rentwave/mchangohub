
"""Management command for wallet health checks."""

from django.core.management.base import BaseCommand
import json

from billing.utils.service import WalletService


class Command(BaseCommand):
	"""Management command to perform wallet system health checks."""
	
	help = 'Perform comprehensive wallet system health check'
	
	def add_arguments(self, parser):
		parser.add_argument(
			'--account-id',
			type=int,
			help='Check specific account balance reconciliation'
		)
		parser.add_argument(
			'--export-json',
			action='store_true',
			help='Export results as JSON'
		)
	
	def handle(self, *args, **options):
		self.stdout.write(
			self.style.SUCCESS('Starting wallet system health check...')
		)
		
		if options['account_id']:
			try:
				result = WalletService.reconcile_account_balance(options['account_id'])
				if options['export_json']:
					self.stdout.write(json.dumps(result, indent=2, default=str))
				else:
					self.display_account_reconciliation(result)
			except Exception as e:
				self.stdout.write(
					self.style.ERROR(f'Error checking account {options["account_id"]}: {str(e)}')
				)
		else:
			report = WalletService.get_system_health_report()
			if options['export_json']:
				self.stdout.write(json.dumps(report, indent=2, default=str))
			else:
				self.display_health_report(report)
		
		self.stdout.write(
			self.style.SUCCESS('Health check completed.')
		)
	
	def display_account_reconciliation(self, result):
		"""Display account reconciliation results."""
		self.stdout.write(f"\nAccount: {result['account_number']}")
		self.stdout.write(f"Total actions processed: {result['total_actions_processed']}")
		
		if result['is_balanced']:
			self.stdout.write(
				self.style.SUCCESS('✓ Account balances are properly reconciled')
			)
		else:
			self.stdout.write(
				self.style.ERROR('✗ Balance discrepancies detected:')
			)
			for balance_type, discrepancy in result['discrepancies'].items():
				self.stdout.write(f"  {balance_type}:")
				self.stdout.write(f"    Actual: {discrepancy['actual']}")
				self.stdout.write(f"    Calculated: {discrepancy['calculated']}")
				self.stdout.write(f"    Difference: {discrepancy['difference']}")
	
	def display_health_report(self, report):
		"""Display system health report."""
		self.stdout.write(f"\n=== Wallet System Health Report ===")
		self.stdout.write(f"Generated: {report['timestamp']}")
		self.stdout.write(f"Overall Health: {report['overall_health']}")
		
		accounts = report['accounts']
		self.stdout.write(f"\n--- Accounts ---")
		self.stdout.write(f"Total: {accounts['total']}")
		self.stdout.write(f"Active: {accounts['active']}")
		self.stdout.write(f"Frozen: {accounts['frozen']}")
		self.stdout.write(f"Health Score: {accounts['health_score']:.1f}%")
		
		balances = report['balances']
		self.stdout.write(f"\n--- System Balances ---")
		for balance_type, total in balances.items():
			if total:
				self.stdout.write(f"{balance_type.replace('total_', '').title()}: {total:,.2f}")
		
		transactions = report['transactions']
		self.stdout.write(f"\n--- Transactions ---")
		self.stdout.write(f"Pending: {transactions['pending']}")
		self.stdout.write(f"Failed: {transactions['failed']}")
		self.stdout.write(f"Recent (24h): {transactions['recent_24h']}")
		
		# Issues
		if report['issues']:
			self.stdout.write(f"\n--- Issues Detected ---")
			for issue in report['issues']:
				self.stdout.write(self.style.WARNING(f"⚠ {issue}"))
		else:
			self.stdout.write(
				self.style.SUCCESS('\n✓ No issues detected')
			)