# coding=utf-8
"""
The base interface implementation to help with functions that need to be used across interface functions.
"""
import logging
import time
from decimal import Decimal
from typing import Optional, Any, Dict, Type
from billing.backend.processes import *
from django.db import transaction
from django.core.cache import cache
from audit.backend.audit_management_service import AuditManagementService
from base.backend.service import ExecutionProfileService, RuleProfileService, StateService, BalanceLogEntryService, \
	BalanceLogService
from billing.models import WalletTransaction, WalletAccount

log = logging.getLogger(__name__)


class InterfaceBase(AuditManagementService):
	"""The class with the base helper functions for interfaces."""
	_state_cache: Dict[str, Any] = {}
	_execution_profile_cache: Dict[str, Any] = {}
	_class_cache: Dict[str, Type] = {}
	
	@classmethod
	def _get_cached_state(cls, state_name: str) -> Any:
		"""Get state from cache or database."""
		cache_key = f"state_{state_name}"
		if cache_key not in cls._state_cache:
			cls._state_cache[cache_key] = StateService().get(name=state_name)
		return cls._state_cache[cache_key]
	
	@classmethod
	def _get_cached_execution_profile(cls, profile_name: str) -> Any:
		"""Get execution profile from cache or database."""
		return ExecutionProfileService().get(name=profile_name)
	
	def call_class_method(self, class_instance: object, function_name: str, **kwargs) -> Optional[Any]:
		"""
		Calls the given method on the class instance provided passing in the kwargs
		@param class_instance: The instance of the class to call a function in.
		@param function_name: The function name to call on the class.
		@param kwargs: The arguments to pass to the class method.
		@return: The results of processing the function on the class.
		"""
		if class_instance is None:
			log.error('%s call_class_method: class_instance is None', self.__class__.__name__)
			return None
		if not hasattr(class_instance, function_name):
			log.error('%s call_class_method: method %s not found on %s',
			          self.__class__.__name__, function_name, type(class_instance).__name__)
			return None
		try:
			method = getattr(class_instance, function_name)
			return method(**kwargs)
		except Exception as e:
			log.exception('%s call_class_method Exception calling %s: %s',
			              self.__class__.__name__, function_name, e)
			return None
	
	def get_class_instance(self, class_name: str, **kwargs) -> Optional[object]:
		"""
		Retrieves the instance of the class provided instantiated with parameters.
		@param class_name: The class name we are trying to instantiate.
		@param kwargs: Any key word arguments to be passed to the class instantiation.
		@return: The instantiated class instance.
		"""
		if class_name in self._class_cache:
			try:
				return self._class_cache[class_name](**kwargs)
			except Exception as e:
				log.exception('%s get_class_instance cached class instantiation failed for %s: %s',
				              self.__class__.__name__, class_name, e)
				return None
		try:
			if class_name in globals():
				class_object = globals()[class_name]
				if hasattr(class_object, '__class__') or callable(class_object):
					self._class_cache[class_name] = class_object
					return class_object(**kwargs)
				else:
					log.error('%s get_class_instance: %s is not a class or callable', self.__class__.__name__, class_name)
			else:
				log.error('%s get_class_instance: class %s not found in globals',
				          self.__class__.__name__, class_name)
		except Exception as e:
			log.exception('%s get_class_instance Exception: %s', self.__class__.__name__, e)
		
		return None
	
	def execute(
			self,
			transaction_history,
			account,
			amount: Decimal,
			balance_entry_type,
			reference: Optional[str] = None,
			description: Optional[str] = None,
			**kwargs
	) -> Optional[Any]:
		"""
		This handles calling of Rule Profiles accordingly. This method is responsible for creating the log entry
		accordingly.
		@param transaction_history: The transaction_history we are currently executing.
		@param account: The account being operated on
		@param amount: The amount being transacted.
		@param balance_entry_type: The balance entry type we are currently logging for this activity.
		@param reference: The transaction reference we are working with now.
		@param description: The description of this execution step.
		@param kwargs: The arguments to pass to our execute method of our classes.
		@return: The results of processing the calls to the classes.
		"""
		execution_profile = self._get_cached_execution_profile(self.__class__.__name__)
		if execution_profile is None:
			log.warning('%s execute: No execution profile found for %s',
			            self.__class__.__name__, self.__class__.__name__)
			return None
		rule_profiles = RuleProfileService().filter(
			execution_profile=execution_profile,
		).order_by('order')
		if not rule_profiles.exists():
			log.warning('%s execute: No active rule profiles found', self.__class__.__name__)
			return None
		results = None
		active_state = self._get_cached_state('Active')
		failed_state = self._get_cached_state('Failed')
		completed_state = self._get_cached_state('Completed')
		try:
			with transaction.atomic():
				total_balance = kwargs.get('total_balance', transaction_history.amount)
				receipt = kwargs.get("receipt", None)
				balance_log = BalanceLogService().create(
					transaction=transaction_history,
					balance_entry_type=balance_entry_type,
					reference=reference,
					amount_transacted=amount,
					description=description,
					receipt=receipt,
					state=active_state,
					total_balance=total_balance
				)
				if not balance_log:
					raise Exception('%s Could not create the balance log entry.' % self.__class__.__name__)
				for rule in rule_profiles:
					class_instance = self.get_class_instance(rule.name)
					if class_instance is None:
						BalanceLogService().update(balance_log.id, state=failed_state)
						raise Exception(
							'%s Could not instantiate class: %s' % (self.__class__.__name__, rule.name)
						)
					results = self.call_class_method(
						class_instance, 'process',
						balance_log=balance_log,
						account=account,
						amount=amount,
						balance_entry_type=balance_entry_type,
						reference=reference,
						description=description,
						**kwargs
					)
					print("Results from %s: %s" % (rule.name, results))
					if results is None:
						BalanceLogService().update(balance_log.id, state=failed_state)
						raise Exception(
							'%s Execution error, got results: %s for rule profile: %s' % (
								self.__class__.__name__, results, rule.name)
						)
					if rule.sleep_seconds > 0:
						time.sleep(rule.sleep_seconds)
				BalanceLogService().update(balance_log.id, state=completed_state)
		except Exception as e:
			log.exception('%s execute: Transaction failed: %s', self.__class__.__name__, e)
			raise
		
		return results
	
	def post(self, **kwargs) -> Any:
		"""
		The method that handles the execution of commands.
		@param kwargs: The arguments to pass down to the execute method.
		@return: The results of processing the results.
		"""
		raise NotImplementedError("This method MUST be implemented by the super class!")
	
	def initiate_transaction(
			self,
			contribution,
			transaction_type: str,
			amount: Decimal,
			reference: str,
			description: Optional[str],
			**kwargs
	) -> WalletTransaction:
		"""Creates the transaction history for the interface transaction."""
		try:
			state_active = self._get_cached_state('Active')
			kwargs.setdefault("state", state_active)
			account = WalletAccount.objects.select_for_update().get(contribution=contribution)
			if transaction_type == "CR":
				transaction_history = account.initiate_topup(
					amount=amount, reference=reference, description=description
				)
			else:
				transaction_history = account.initiate_payment(amount=amount, reference=reference, description=description)
			if transaction_history is None:
				raise Exception(
					'%s Could not create a process for: %s' % (self.__class__.__name__, contribution)
				)
			return transaction_history
		except Exception as e:
			log.exception('%s create_transaction_history Exception: %s', self.__class__.__name__, e)
			raise Exception('%s Could not create Transaction History. Server Error.' % self.__class__.__name__)
	
	def approve_transaction(self, transaction_id: int, contribution, transaction_type: str, description, receipt) -> WalletTransaction:
		"""Fail a particular transaction history"""
		complete_state = self._get_cached_state("Completed")
		try:
			account = WalletAccount.objects.select_for_update().get(contribution=contribution)
			transaction_obj = WalletTransaction.objects.get(pk=transaction_id)
			if transaction_type == "CR":
				account.topup_approved(amount=transaction_obj.amount, reference=transaction_obj.reference, description=description, receipt=receipt,)
			else:
				account.payment_approved(amount=transaction_obj.amount, reference=transaction_obj.reference, description=description, receipt=receipt,)
			balance_logs = BalanceLogService().filter(transaction=transaction_obj)
			balance_log_ids = list(balance_logs.values_list('id', flat=True))
			if balance_log_ids:
				BalanceLogService().filter(id__in=balance_log_ids).update(state=complete_state)
				balance_log_entries = BalanceLogEntryService().filter(process_log__id__in=balance_log_ids)
				print(balance_log_entries)
				if balance_log_entries:
					balance_log_entries.update(state=complete_state)
			return transaction_obj
		except WalletTransaction.DoesNotExist:
			log.error('%s fail_transaction_history: Transaction %s not found',
			          self.__class__.__name__, transaction_id)
			raise Exception('%s Transaction History not found.' % self.__class__.__name__)
		except Exception as e:
			log.exception('%s fail_transaction_history Exception: %s', self.__class__.__name__, e)
			raise Exception('%s Could not fail the Transaction History. Server Error.' % self.__class__.__name__)
		
	def reject_transaction(self, transaction_id: int, contribution, transaction_type: str, description) -> WalletTransaction:
		"""Fail a particular transaction history"""
		failed_state = self._get_cached_state("Failed")
		try:
			account = WalletAccount.objects.select_for_update().get(contribution=contribution)
			transaction_obj = WalletTransaction.objects.get(pk=transaction_id)
			if transaction_type == "CR":
				account.topup_rejected(amount=transaction_obj.amount, reference=transaction_obj.reference, description=description)
			else:
				account.payment_rejected(amount=transaction_obj.amount, reference=transaction_obj.reference, description=description)
			balance_logs = BalanceLogService().filter(transaction=transaction_obj)
			balance_log_ids = list(balance_logs.values_list('id', flat=True))
			if balance_log_ids:
				BalanceLogService().filter(id__in=balance_log_ids).update(state=failed_state)
				balance_log_entries = BalanceLogEntryService().filter(process_log__id__in=balance_log_ids)
				balance_log_entries.update(state=failed_state)
			return transaction_obj
		except WalletTransaction.DoesNotExist:
			log.error('%s fail_transaction_history: Transaction %s not found',
			          self.__class__.__name__, transaction_id)
			raise Exception('%s Transaction History not found.' % self.__class__.__name__)
		except Exception as e:
			log.exception('%s fail_transaction_history Exception: %s', self.__class__.__name__, e)
			raise Exception('%s Could not fail the Transaction History. Server Error.' % self.__class__.__name__)