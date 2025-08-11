import logging

from billing.backend.processes.base import ProcessorBase

log = logging.getLogger(__name__)


class InitiateTopup(ProcessorBase):
	"""Monthly Deduction initialization processes"""

	def credit_account_uncleared(self, account, balance_log, amount, **kwargs):
		"""Debits the account's available balance"""
		return self.debit(account, balance_log, 'uncleared', amount, **kwargs)

	def credit_account_current(self, account, balance_log, amount, **kwargs):
		"""Credits the account's reserved balance"""
		return self.credit(account, balance_log, 'current', amount, **kwargs)


class ApproveTopupTransaction(ProcessorBase):
	"""Monthly Deduct Approval processes"""

	def debit_account_uncleared(self, account, balance_log, amount, **kwargs):
		"""Debits the account's current balance"""
		return self.debit(account, balance_log, 'uncleared', amount, **kwargs)

	def credit_account_available(self, account, balance_log, amount, **kwargs):
		"""Debits the account's reserved balance"""
		return self.debit(account, balance_log, 'available', amount, **kwargs)


class RejectTopupTransaction(ProcessorBase):
	"""Monthly Deduct Approval processes"""

	def debit_account_current(self, account, balance_log, amount, **kwargs):
		"""Debits the account's current balance"""
		return self.debit(account, balance_log, 'current', amount, **kwargs)

	def debit_account_uncleared(self, account, balance_log, amount, **kwargs):
		"""Debits the account's reserved balance"""
		return self.debit(account, balance_log, 'uncleared', amount, **kwargs)

