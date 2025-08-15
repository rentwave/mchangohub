import logging
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, Optional, Union
from django.db import transaction
from contributions.backend.services import ContributionService

import logging
from typing import Dict, Any, Optional
from django.db import transaction as trx

from base.backend.service import (
    WalletTransactionService,
    BalanceEntryTypeService,
    WalletAccountService,
    StateService
)
from billing.backend.interfaces.base import InterfaceBase

log = logging.getLogger(__name__)

logger = logging.getLogger(__name__)


class InitiateTopup(InterfaceBase):
    ERROR_CODES = {
        'CONTRIBUTION_NOT_FOUND': {"code": "400.001", 'message': 'Contribution does not exist'},
        'AMOUNT_NOT_PROVIDED': {"code": "400.002", 'message': 'Amount not provided or invalid'},
        'AMOUNT_INVALID': {"code": "400.003", 'message': 'Amount must be a positive number'},
        'PHONE_NOT_PROVIDED': {"code": "400.004", 'message': 'Phone number not provided'},
        'PHONE_INVALID': {"code": "400.005", 'message': 'Phone number format is invalid'},
        'ACCOUNT_NOT_EXISTS': {"code": "400.006", 'message': 'Contribution account does not exist'},
        'BALANCE_ENTRY_TYPE_NOT_FOUND': {"code": "400.007", 'message': 'Balance entry type not configured'},
        'TRANSACTION_CREATION_FAILED': {"code": "500.001", 'message': 'Failed to create transaction'},
        'TRANSACTION_EXECUTION_FAILED': {"code": "500.002", 'message': 'Failed to execute transaction'},
        'TRANSACTION_FAILED': {"code": "500.003", "message": "Transaction failed due to system error"},
        'SUCCESS': {"code": "200.000", "message": "Transaction initiated successfully"}
    }
    _balance_entry_type_cache: Optional[Any] = None
    _active_state_cache: Optional[Any] = None
    _failed_state_cache: Optional[Any] = None
    
    @classmethod
    def _get_balance_entry_type(cls) -> Optional[Any]:
        print(BalanceEntryTypeService().get(name="InitiateTopUp"))
        return BalanceEntryTypeService().get(name="InitiateTopUp")
    
    @classmethod
    def _get_active_state(cls) -> Optional[Any]:
        if cls._active_state_cache is None:
            cls._active_state_cache = StateService().get(name="Active")
        return cls._active_state_cache
    
    @classmethod
    def _get_failed_state(cls) -> Optional[Any]:
        if cls._failed_state_cache is None:
            cls._failed_state_cache = StateService().get(name="Failed")
        return cls._failed_state_cache
    
    def _validate_phone_number(self, phone_number: str) -> bool:
        if not phone_number or not isinstance(phone_number, str):
            return False
        phone_cleaned = phone_number.strip().replace(' ', '').replace('-', '')
        if not phone_cleaned.isdigit() or len(phone_cleaned) < 10 or len(phone_cleaned) > 15:
            return False
        return True
    
    def _validate_amount(self, amount: Union[str, int, float, Decimal]) -> tuple[bool, Optional[Decimal]]:
        if not amount:
            return False, None
        try:
            decimal_amount = Decimal(str(amount))
            if decimal_amount <= 0:
                return False, None
            if decimal_amount > Decimal('1000000'):
                return False, None
            if decimal_amount.as_tuple().exponent < -2:
                return False, None
            return True, decimal_amount
        except (ValueError, TypeError, InvalidOperation):
            return False, None
    
    def _validate_inputs(self, contribution_id: int, **kwargs) -> Optional[Dict[str, Any]]:
        if not contribution_id:
            return self.ERROR_CODES['CONTRIBUTION_NOT_FOUND']
        try:
            contribution = ContributionService().get(
                id=contribution_id,
            )
            print(contribution)
            if not contribution:
                return self.ERROR_CODES['CONTRIBUTION_NOT_FOUND']
        except Exception:
            return self.ERROR_CODES['CONTRIBUTION_NOT_FOUND']
        amount = kwargs.get("amount")
        is_valid_amount, decimal_amount = self._validate_amount(amount)
        if not is_valid_amount:
            return self.ERROR_CODES['AMOUNT_NOT_PROVIDED'] if not amount else self.ERROR_CODES['AMOUNT_INVALID']
        phone_number = kwargs.get("phone_number", "").strip()
        if not phone_number:
            return self.ERROR_CODES['PHONE_NOT_PROVIDED']
        if not self._validate_phone_number(phone_number):
            return self.ERROR_CODES['PHONE_INVALID']
        return None
    
    def _get_wallet_account(self, contribution) -> Optional[Any]:
        try:
            return WalletAccountService(True).get(
                contribution=contribution,
            )
        except Exception as e:
            logger.exception("Error fetching wallet account for contribution %s: %s", contribution.id, e)
            return None
    
    def _check_account_exists(self, contribution) -> bool:
        try:
            return WalletAccountService().filter(
                contribution=contribution,
            ).exists()
        except Exception as e:
            logger.exception("Error checking account existence for contribution %s: %s", contribution.id, e)
            return False
    
    def _process_transaction(self, contribution, amount: Decimal, phone_number: str, ref: str, charge) -> Dict[str, Any]:
        transaction_history = None
        try:
            with transaction.atomic():
                print(contribution)
                account = self._get_wallet_account(contribution)
                print(account)
                if not account:
                    return self.ERROR_CODES['ACCOUNT_NOT_EXISTS']
                balance_entry_type = self._get_balance_entry_type()
                if not balance_entry_type:
                    return self.ERROR_CODES['BALANCE_ENTRY_TYPE_NOT_FOUND']
                description = f"Contribution Request to {contribution.name} by {phone_number}"
                detailed_description = f"{description} with ref {ref}"
                try:
                    transaction_history = self.initiate_transaction(
                        contribution=contribution,
                        transaction_type="CR",
                        amount=amount,
                        reference=ref,
                        charge=charge,
                        description=description,
                    )
                    if not transaction_history:
                        return self.ERROR_CODES['TRANSACTION_CREATION_FAILED']
                except Exception as e:
                    logger.exception("Failed to initiate transaction: %s", e)
                    return self.ERROR_CODES['TRANSACTION_CREATION_FAILED']
                try:
                    top_up_result = self.execute(
                        transaction_history=transaction_history,
                        account=account,
                        amount=amount,
                        balance_entry_type=balance_entry_type,
                        reference=ref,
                        description=detailed_description
                    )
                    if not top_up_result:
                        self.reject_transaction(transaction_id=transaction_history.id,
                                                contribution=account.contribution, transaction_type="CR",
                                                description="Transaction failed")
                        return self.ERROR_CODES['TRANSACTION_EXECUTION_FAILED']
                except Exception as e:
                    logger.exception("Failed to execute transaction: %s", e)
                    if transaction_history:
                        self.reject_transaction(transaction_id=transaction_history.id, contribution=account.contribution, transaction_type="CR", description="Transaction failed")
                    return self.ERROR_CODES['TRANSACTION_EXECUTION_FAILED']
                logger.info(
                    "Successfully initiated topup for contribution %s, amount %s, reference %s",
                    contribution.id,
                    amount,
                    ref
                )
                success_response = self.ERROR_CODES['SUCCESS'].copy()
                success_response.update({
                    'transaction_reference': ref,
                    'amount': str(amount),
                    'contribution_name': contribution.name
                })
                return success_response
        except Exception as e:
            logger.exception("Unexpected error in transaction processing: %s", e)
            if transaction_history:
                try:
                    self.reject_transaction(transaction_id=transaction_history.id, contribution=account.contribution,
                                            transaction_type="CR", description="Transaction failed")
                except Exception as cleanup_error:
                    logger.exception("Failed to cleanup failed transaction: %s", cleanup_error)
            return self.ERROR_CODES['TRANSACTION_FAILED']
    
    def post(self, contribution_id: int, request=None, **kwargs) -> Dict[str, Any]:
        try:
            validation_result = self._validate_inputs(contribution_id, **kwargs)
            if validation_result:
                return validation_result
            contribution = ContributionService().get(
                id=contribution_id
            )
            if not contribution:
                return self.ERROR_CODES['CONTRIBUTION_NOT_FOUND']
            print(self._check_account_exists(contribution))
            if not self._check_account_exists(contribution):
                return self.ERROR_CODES['ACCOUNT_NOT_EXISTS']
            amount = Decimal(str(kwargs["amount"]))
            phone_number = kwargs["phone_number"].strip()
            ref = kwargs["ref"].strip()
            charge = kwargs["ref"].strip()
            return self._process_transaction(contribution, amount, phone_number, ref, charge)
        except Exception as e:
            logger.exception(
                "InitiateTopup.post exception for contribution %s: %s",
                contribution_id,
                e
            )
            return self.ERROR_CODES['TRANSACTION_FAILED']


class ApproveTopupTransaction(InterfaceBase):
    _balance_entry_type_cache: Optional[Any] = None
    _active_state_cache: Optional[Any] = None

    @classmethod
    def _get_balance_entry_type(cls) -> Any:
        if cls._balance_entry_type_cache is None:
            cls._balance_entry_type_cache = BalanceEntryTypeService().get(name="ApproveTopupTransaction")
        return cls._balance_entry_type_cache

    @classmethod
    def _get_active_state(cls) -> Any:
        if cls._active_state_cache is None:
            cls._active_state_cache = StateService().get(name="Active")
        return cls._active_state_cache

    def _get_latest_transaction(self, reference: str) -> Optional[Any]:
        try:
            return (
                WalletTransactionService()
                .filter(reference=reference)
                .order_by("-date_created")
                .first()
            )
        except Exception as e:
            log.exception("Error fetching transaction for reference %s: %s", reference, e)
            return None

    def _get_wallet_account(self, contribution, active_state) -> Optional[Any]:
        try:
            return (
                WalletAccountService(True)
                .get(contribution=contribution, state=active_state)
            )
        except Exception as e:
            log.exception("Error fetching wallet account for contribution %s: %s", contribution, e)
            return None

    def _validate_transaction_data(self, transaction_history, balance_entry_type, account) -> Dict[str, str]:
        if not transaction_history:
            return {"code": "300.003", "message": "Transaction not found"}
        if not balance_entry_type:
            return {"code": "300.004", "message": "Balance entry type not found"}
        if not account:
            return {"code": "300.005", "message": "Account not found"}
        if transaction_history.amount <= 0:
            return {"code": "300.006", "message": "Invalid transaction amount"}
        return {}

    def post(self, request, reference: str, receipt: str,  **kwargs) -> Dict[str, Any]:
        if not reference:
            return {"code": "300.001", "message": "Reference is required"}
        try:
            balance_entry_type = self._get_balance_entry_type()
            transaction_history = self._get_latest_transaction(reference)
            print(transaction_history)
            if not transaction_history:
                return {"code": "300.003", "message": "Transaction not found"}
            validation_error = self._validate_transaction_data(transaction_history, balance_entry_type, transaction_history.wallet_account)
            if validation_error:
                return validation_error
            try:
                with trx.atomic():
                    description = (
                        f"Contribution approved for {transaction_history.wallet_account.contribution.name} "
                        f"with reference {transaction_history.reference}"
                    )
                    approved_transaction = self.approve_transaction(
                        transaction_id=transaction_history.id,
                        contribution=transaction_history.wallet_account.contribution,
                        transaction_type="CR",
                        description=description,
                        receipt=receipt,
                    )
                    if not approved_transaction:
                        raise Exception("Failed to approve transaction")
                    approval_result = self.execute(
                        transaction_history=approved_transaction,
                        account=transaction_history.wallet_account,
                        amount=transaction_history.amount,
                        balance_entry_type=balance_entry_type,
                        reference=reference,
                        description=description,
                    )
                    print("Approval Result is :", approval_result)
                    if approval_result is None:
                        raise Exception("Unable to process the approved transaction")
                    log.info(
                        "Successfully approved transaction %s for contribution %s with amount %s",
                        reference,
                        transaction_history.wallet_account.contribution.name,
                        transaction_history.amount,
                    )
                    return {
                        "code": "200.001",
                        "message": "Transaction approved successfully",
                        "transaction_id": approved_transaction.id,
                        "amount": str(transaction_history.amount),
                    }
            except Exception as transaction_error:
                log.exception("Transaction processing failed for reference %s: %s",reference, transaction_error)
                try:
                    if hasattr(transaction_history, "id"):
                        self.reject_transaction(transaction_id=transaction_history.id, contribution=transaction_history.wallet_account.contribution, transaction_type= "CR", description="Transaction failed")
                except Exception as fail_error:
                    log.exception( "Failed to mark transaction as failed for reference %s: %s",reference, fail_error)
                return {"code": "300.007", "message": f"Transaction processing failed: {str(transaction_error)}"}
        except Exception as ex:
            log.exception("ApproveTopupTransaction: post exception for reference %s: %s", reference, ex)
            return {"code": "500.001", "message": "Transaction approval failed due to system error"}


class RejectTopupTransaction(InterfaceBase):
    _balance_entry_type_cache: Optional[Any] = None
    _active_state_cache: Optional[Any] = None

    @classmethod
    def _get_balance_entry_type(cls) -> Any:
        if cls._balance_entry_type_cache is None:
            cls._balance_entry_type_cache = BalanceEntryTypeService().get(name="RejectTopupTransaction")
        return cls._balance_entry_type_cache

    @classmethod
    def _get_active_state(cls) -> Any:
        if cls._active_state_cache is None:
            cls._active_state_cache = StateService().get(name="Active")
        return cls._active_state_cache

    def _get_latest_transaction(self, reference: str) -> Optional[Any]:
        try:
            return (
                WalletTransactionService()
                .filter(reference=reference)
                .order_by("-date_created")
                .first()
            )
        except Exception as e:
            log.exception("Error fetching transaction for reference %s: %s", reference, e)
            return None

    def _get_wallet_account(self, contribution, active_state) -> Optional[Any]:
        try:
            return (
                WalletAccountService(True)
                .get(contribution=contribution, state=active_state)
            )
        except Exception as e:
            log.exception("Error fetching wallet account for contribution %s: %s", contribution, e)
            return None

    def _validate_transaction_data(self, transaction_history, balance_entry_type, account) -> Dict[str, str]:
        if not transaction_history:
            return {"code": "300.003", "message": "Transaction not found"}
        if not balance_entry_type:
            return {"code": "300.004", "message": "Balance entry type not found"}
        if not account:
            return {"code": "300.005", "message": "Account not found"}
        if transaction_history.amount <= 0:
            return {"code": "300.006", "message": "Invalid transaction amount"}
        return {}

    def post(self, request, reference: str, status: str, **kwargs) -> Dict[str, Any]:
        if not reference:
            return {"code": "300.001", "message": "Reference is required"}
        if not status:
            return {"code": "300.002", "message": "Status is required"}
        try:
            balance_entry_type = self._get_balance_entry_type()
            active_state = self._get_active_state()
            transaction_history = self._get_latest_transaction(reference)
            if not transaction_history:
                return {"code": "300.003", "message": "Transaction not found"}
            account = self._get_wallet_account(transaction_history.account.contribution, active_state)
            validation_error = self._validate_transaction_data(transaction_history, balance_entry_type, account)
            if validation_error:
                return validation_error
            try:
                with trx.atomic():
                    description = (
                        f"Contribution approved for {account.contribution.name} "
                        f"with reference {transaction_history.reference}"
                    )
                    rejected_transaction = self.reject_transaction(
                        transaction_id=transaction_history.id,
                        contribution=account.contribution,
                        transaction_type="CR",
                        description=description,
                    )
                    if not rejected_transaction:
                        raise Exception("Failed to approve transaction")
                    rejection_result = self.execute(
                        transaction_history=rejected_transaction,
                        account=account,
                        amount=transaction_history.amount,
                        balance_entry_type=balance_entry_type,
                        reference=reference,
                        description=description,
                    )
                    if not rejection_result:
                        raise Exception("Unable to process the rejected transaction")
                    log.info(
                        "Successfully approved transaction %s for contribution %s with amount %s",
                        reference,
                        account.contribution.name,
                        transaction_history.amount,
                    )
                    return {
                        "code": "200.001",
                        "message": "Transaction rejected successfully",
                        "transaction_id": rejected_transaction.id,
                        "amount": str(transaction_history.amount),
                    }
            except Exception as transaction_error:
                log.exception("Transaction processing failed for reference %s: %s",reference, transaction_error)
                try:
                    if hasattr(transaction_history, "id"):
                        self.reject_transaction(transaction_id=transaction_history.id, contribution=account.contribution, transaction_type= "CR", description="Transaction failed")
                except Exception as fail_error:
                    log.exception( "Failed to mark transaction as failed for reference %s: %s",reference, fail_error)
                return {"code": "300.007", "message": f"Transaction processing failed: {str(transaction_error)}"}
        except Exception as ex:
            log.exception("ApproveTopupTransaction: post exception for reference %s: %s", reference, ex)
            return {"code": "500.001", "message": "Transaction approval failed due to system error"}
