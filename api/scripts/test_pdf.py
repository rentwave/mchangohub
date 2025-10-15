# QuerySet [<BalanceLogEntry: payment - 30.00 - A0H5NTKUYW1760541111 (Completed ) InitiatePayment : 30.00 Available  30.00>, <BalanceLogEntry: payment - 30.00 - A0H5NTKUYW1760541111 (Completed ) InitiatePayment : 30.00 Reserved  30.00>]>
#
# debit_account_current - ApprovePaymentTransaction  ApprovePaymentTransaction - Active
#
# 67.00
#
# debit_account_reserved - ApprovePaymentTransaction  ApprovePaymentTransaction - Active
#
# 0.00
#
# Results from ApprovePaymentTransaction: 0.00
#
# Transaction processing failed for reference A0H5NTKUYW1760541111: Unable to process the approved transaction
#
# Traceback (most recent call last):
#
#   File "/usr/src/app/billing/backend/interfaces/payment.py", line 315, in post
#
#     raise Exception("Unable to process the approved transaction")
#
# Exception: Unable to process the approved transaction
#
# ApprovePaymentTransaction fail_transaction_history Exception: ['No pending topup transaction found for reference: A0H5NTKUYW1760541111']
#
# Traceback (most recent call last):
#
#   File "/usr/src/app/billing/backend/interfaces/payment.py", line 315, in post
#
#     raise Exception("Unable to process the approved transaction")
#
# Exception: Unable to process the approved transaction
#
# During handling of the above exception, another exception occurred:
#
# Traceback (most recent call last):
#
#   File "/usr/src/app/billing/models.py", line 573, in topup_rejected
#
#     transaction_obj = WalletTransaction.objects.get(
#
#                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#
#   File "/usr/local/lib/python3.11/site-packages/django/db/models/manager.py", line 87, in manager_method
#
#     return getattr(self.get_queryset(), name)(*args, **kwargs)
#
#            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#
#   File "/usr/local/lib/python3.11/site-packages/django/db/models/query.py", line 633, in get
#
#     raise self.model.DoesNotExist(
#
# billing.models.WalletTransaction.DoesNotExist: WalletTransaction matching query does not exist.
#
# During handling of the above exception, another exception occurred:
#
# Traceback (most recent call last):
#
#   File "/usr/src/app/billing/backend/interfaces/base.py", line 254, in reject_transaction
#
#     account.topup_rejected(amount=transaction_obj.amount, reference=transaction_obj.reference, description=description)
#
#   File "/usr/local/lib/python3.11/contextlib.py", line 81, in inner
#
#     return func(*args, **kwds)
#
#            ^^^^^^^^^^^^^^^^^^^
#
#   File "/usr/src/app/billing/models.py", line 580, in topup_rejected
#
#     raise ValidationError(f"No pending topup transaction found for reference: {reference}")
#
# django.core.exceptions.ValidationError: ['No pending topup transaction found for reference: A0H5NTKUYW1760541111']
#
# Failed to mark transaction as failed for reference A0H5NTKUYW1760541111: ApprovePaymentTransaction Could not fail the Transaction History. Server Error.
#
# Traceback (most recent call last):
#
# 172.20.0.1 - - [15/Oct/2025:18:12:42 +0300] "POST /api/billing/api/v1/callbacks/b2c/ HTTP/1.1" 200 326 "-" "python-requests/2.32.5"
#
#   File "/usr/src/app/billing/backend/interfaces/payment.py", line 315, in post
#
#     raise Exception("Unable to process the approved transaction")
#
# Exception: Unable to process the approved transaction
#
# During handling of the above exception, another exception occurred:
#
# Traceback (most recent call last):
#
#   File "/usr/src/app/billing/models.py", line 573, in topup_rejected
#
#     transaction_obj = WalletTransaction.objects.get(
#
#                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#
#   File "/usr/local/lib/python3.11/site-packages/django/db/models/manager.py", line 87, in manager_method
#
#     return getattr(self.get_queryset(), name)(*args, **kwargs)
#
#            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#
#   File "/usr/local/lib/python3.11/site-packages/django/db/models/query.py", line 633, in get
#
#     raise self.model.DoesNotExist(
#
# billing.models.WalletTransaction.DoesNotExist: WalletTransaction matching query does not exist.
#
# During handling of the above exception, another exception occurred:
#
# Traceback (most recent call last):
#
#   File "/usr/src/app/billing/backend/interfaces/base.py", line 254, in reject_transaction
#
#     account.topup_rejected(amount=transaction_obj.amount, reference=transaction_obj.reference, description=description)
#
#   File "/usr/local/lib/python3.11/contextlib.py", line 81, in inner
#
#     return func(*args, **kwds)
#
#            ^^^^^^^^^^^^^^^^^^^
#
#   File "/usr/src/app/billing/models.py", line 580, in topup_rejected
#
#     raise ValidationError(f"No pending topup transaction found for reference: {reference}")
#
# django.core.exceptions.ValidationError: ['No pending topup transaction found for reference: A0H5NTKUYW1760541111']
#
# During handling of the above exception, another exception occurred:
#
# Traceback (most recent call last):
#
#   File "/usr/src/app/billing/backend/interfaces/payment.py", line 332, in post
#
#     self.reject_transaction(transaction_id=transaction_history.id, contribution=account.contribution, transaction_type= "CR", description="Transaction failed")
#
#   File "/usr/src/app/billing/backend/interfaces/base.py", line 270, in reject_transaction
#
#     raise Exception('%s Could not fail the Transaction History. Server Error.' % self.__class__.__name__)
#
# Exception: ApprovePaymentTransaction Could not fail the Transaction History. Server Error.