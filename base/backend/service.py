from base.models import RuleProfile, RuleProfileCommand, EntryType, BalanceEntryType, State, AccountFieldType
from billing.models import BalanceLogEntry, BalanceLog, WalletAccount, WalletTransaction
from utils.service_base import ServiceBase


class ExecutionProfileService(ServiceBase):
	"""
	ExecutionProfile model CRUD services
	"""
	manager = ExecutionProfile.objects


class RuleProfileService(ServiceBase):
	"""
	RuleProfile model CRUD services
	"""
	manager = RuleProfile.objects


class RuleProfileCommandService(ServiceBase):
	"""
	RuleProfileCommand model CRUD services
	"""
	manager = RuleProfileCommand.objects


class BalanceLogEntryService(ServiceBase):
	"""
	BalanceLogEntry model CRUD services
	"""
	manager = BalanceLogEntry.objects


class EntryTypeService(ServiceBase):
	"""
	EntryType model CRUD services
	"""
	manager = EntryType.objects


class BalanceEntryTypeService(ServiceBase):
	"""
	BalanceEntryType model CRUD services
	"""
	manager = BalanceEntryType.objects
	
	
class StateService(ServiceBase):
	"""
	BalanceEntryType model CRUD services
	"""
	manager = State.objects
	
	
class BalanceLogService(ServiceBase):
	"""
	BalanceEntryType model CRUD services
	"""
	manager = BalanceLog.objects
	
	

class WalletAccountService(ServiceBase):
	"""
	WalletAccount model CRUD services
	"""
	manager = WalletAccount.objects


class WalletTransactionService(ServiceBase):
	"""
	BalanceEntryType model CRUD services
	"""
	manager = WalletTransaction.objects
	
class AccountFieldTypeService(ServiceBase):
	"""
	BalanceEntryType model CRUD services
	"""
	manager = AccountFieldType.objects