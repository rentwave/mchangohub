from billing.backend.processes.base import ProcessorBase


class InitiatePayment(ProcessorBase):

	def debit_account_available(self, account, balance_log, amount, **kwargs):
		"""Credits the account's uncleared balance"""
		return self.debit(account, balance_log, 'available', amount, **kwargs)

	def credit_account_reserved(self, account, balance_log, amount, **kwargs):
		"""Credits the account's current balance"""
		return self.credit(account, balance_log, 'reserved', amount, **kwargs)


class ApprovePaymentTransaction(ProcessorBase):
	""" Wallet Topup Approval processes """
	
	def debit_account_reserved(self, account, balance_log, amount, **kwargs):
		"""Credits the account's available balance"""
		return self.debit(account, balance_log, 'reserved', amount, **kwargs)

	def debit_account_current(self, account, balance_log, amount, **kwargs):
		"""Debits the account's uncleared balance"""
		return self.debit(account, balance_log, 'current', amount, **kwargs)

	
	
class RejectPaymentTransaction(ProcessorBase):
	"""Monthly Deduct Approval processes"""
	
	def debit_account_reserved(self, account, balance_log, amount, **kwargs):
		"""Debits the account's current balance"""
		return self.debit(account, balance_log, 'reserved', amount, **kwargs)
	
	def credit_account_available(self, account, balance_log, amount, **kwargs):
		"""Debits the account's reserved balance"""
		return self.credit(account, balance_log, 'available', amount, **kwargs)

