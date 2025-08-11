# -*- coding: utf-8 -*-
""" This is a super class for crediting and debiting transactions. """
import logging
from decimal import Decimal

from django.db import transaction

from base.backend.service import RuleProfileService, RuleProfileCommandService, EntryTypeService, StateService, \
	AccountFieldTypeService, BalanceLogEntryService

log = logging.getLogger(__name__)


# noinspection PyProtectedMember
class ProcessorBase(object):
	"""	The ProcessorBase Module Processor	"""

	log_name = ''
	"""	The log name we are maintaining. """

	def __init__(self):
		super(ProcessorBase, self).__init__()
		if self.log_name == '':
			self.log_name = self.__class__.__name__

	def process(self, **kwargs):
		"""	The function to process the rule profile commands accordingly and handle transaction management. """
		rule_profile = RuleProfileService().get(name=self.__class__.__name__)
		results = None
		if rule_profile is not None:
			profile_commands = RuleProfileCommandService().filter(
				rule_profile=rule_profile, state__name="Active").order_by('order')
			with transaction.atomic():
				for command in profile_commands:
					print(command)
					results = self.call_self_method(command.name, **kwargs)
					print(results)
					# if not results:
					# 	raise Exception(
					# 		'%s Processing error, got results: %s for command: %s' % (
					# 			self.__class__.__name__, results, command.name))
		return results

	def serialize_kwargs(self, manager, payload):
		""" Examines the payload against a model and its fields and returns a dictionary of key arguments that match
		what is required by the target model. """
		try:
			key_args = {}
			for x in [f.name for f in manager.model._meta.get_fields()]:
				if x in payload.keys() and x != 'id' and x != 'key':
					key_args[x] = payload[x]
			return key_args
		except Exception as e:
			log.exception('%s serialize_kwargs Exception: %s', self.log_name, e)
		return payload

	def call_instance_method(self, class_name, function_name, **kwargs):
		""" Calls the given function name on the class identified by class name passing in the given kwargs to the
		function. The class constructor should therefore not have parameters. """
		try:
			return getattr(self.get_class_instance(class_name), function_name)(**kwargs)
		except Exception as e:
			log.exception('%s call_instance_method Exception: %s', self.log_name, e)
		return None

	def call_self_method(self, function_name, **kwargs):
		""" Calls the given function name on the current class passing in the given kwargs to the function. The class
		constructor should therefore not have parameters. """
		try:
			return getattr(self, function_name)(**kwargs)
		except Exception as e:
			log.exception('%s call_self_method Exception: %s', self.log_name, e)
		return None

	def get_class_instance(self, class_name, **kwargs):
		""" Retrieves the instance of the class provided instantiated without parameters. """
		try:
			if class_name in globals() and hasattr(globals()[class_name], '__class__'):
				class_object = globals()[class_name]
				return class_object(**kwargs)
		except Exception as e:
			log.exception('%s get_class_instance Exception: %s', self.log_name, e)
		return None

	@staticmethod
	def set_attributes_if_any(obj, *exempt, **kwargs):
		""" Sets the attributes of the object if they exists in the given kwargs but not in the except args. """
		try:
			if obj is not None:
				for k, v in kwargs.items():
					if k not in exempt:
						if hasattr(obj, k):
							setattr(obj, k, v)
				if hasattr(obj, 'save'):
					obj.save()
				return obj
		except Exception as e:
			log.exception('Exception: %s', e)
		return None

	def credit(self, account, process_log, balance_type, amount, **kwargs):
		""" Credits the account accordingly using the process log and logs a balance log. """
		try:
			if not account:
				raise Exception('CREDIT: The requested account was not found for this user!')
			amount_transacted = Decimal(str(round(float(amount), 2)))
			balance_type = str(balance_type).lower()
			manager = BalanceLogEntryService().manager
			pay = {
				"account_field_type": AccountFieldTypeService().get(name=balance_type.title()),
				"process_log": process_log, "amount_transacted": amount_transacted,
				"entry_type": EntryTypeService().get(name="Cr"), "state": StateService().get(name='Completed')
			}
			new_balance = Decimal(getattr(account, balance_type)) + amount_transacted
			pay = dict(pay, **kwargs)
			pay = self.serialize_kwargs(manager, pay)
			balance_log = manager.create(**pay)
			if balance_log is not None:
				return new_balance
		except Exception as e:
			log.exception('%s credit Exception: %s', self.log_name, e)
		return None

	def debit(self, account, process_log, balance_type, amount, **kwargs):
		""" Debits the account, logging the balance log correctly. """
		try:
			# account = getattr(process_log.process, 'account')
			if not account:
				raise Exception('DEBIT: The requested account was not found for this user!')
			amount_transacted = Decimal(str(round(float(amount), 2)))
			balance_type = str(balance_type).lower()
			manager = BalanceLogEntryService().manager
			pay = {
				"account_field_type": AccountFieldTypeService().get(name=balance_type.title()),
				"process_log": process_log, "amount_transacted": amount_transacted,
				"entry_type": EntryTypeService().get(name="Dr"), 'state': StateService().get(name='Completed')
			}
			new_balance = Decimal(getattr(account, balance_type)) - amount_transacted
			pay = dict(pay, **kwargs)
			pay = self.serialize_kwargs(manager, pay)
			balance_log = manager.create(**pay)
			if balance_log is not None:
				return new_balance
		except Exception as e:
			log.exception('%s debit Exception: %s', self.log_name, e)
		return None
