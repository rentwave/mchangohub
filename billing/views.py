import json
import time
import logging
from datetime import datetime
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.urls import re_path, path
from billing.backend.interfaces.topup import InitiateTopup, ApproveTopupTransaction
from billing.backend.interfaces.payment import InitiatePayment, ApprovePaymentTransaction
from billing.helpers.generate_unique_ref import TransactionRefGenerator
from billing.itergrations.pesaway import PesaWayAPIClient

lgr = logging.getLogger(__name__)

def unpack_request_data(request):
	"""
	Retrieves the request data irrespective of the method and type it was send.
	@param request: The Django HttpRequest.
	@type request: WSGIRequest
	@return: The data from the request as a dict
	@rtype: QueryDict
	"""
	try:
		data = None
		if request is not None:
			request_meta = getattr(request, 'META', {})
			request_method = getattr(request, 'method', None)
			if request_meta.get('CONTENT_TYPE', '') == 'application/json':
				data = json.loads(request.body)
			elif str(request_meta.get('CONTENT_TYPE', '')).startswith('multipart/form-data;'):  # Special handling for
				data = request.POST.copy()
				data = data.dict()
			elif request_method == 'GET':
				data = request.GET.copy()
				data = data.dict()
			elif request_method == 'POST':
				data = request.POST.copy()
				data = data.dict()
			if not data:
				request_body = getattr(request, 'body', None)
				if request_body:
					data = json.loads(request_body)
				else:
					data = dict()
			return data
	except Exception as e:
		return dict()


class PesaWayWalletInterface:
	def __init__(self, client_id, client_secret):
		self.pesaway = PesaWayAPIClient(client_id, client_secret)
	
	@csrf_exempt
	def wallet_balance(self, request):
		start = time.time()
		try:
			balance = self.pesaway.get_account_balance()
			return JsonResponse(balance)
		except Exception as e:
			lgr.exception("Error occurred during fetching of wallet balance: %s", e)
			return JsonResponse({"code": "999.999.999"}, status=500)
		finally:
			lgr.info("taken %.2f seconds to get wallet_balance", time.time() - start)
	
	@csrf_exempt
	def mobile_money_transfer(self, request):
		start = time.time()
		try:
			request_data = unpack_request_data(request)
			amount = request_data.get("amount")
			currency = request_data.get("currency")
			recipient_number = request_data.get("recipient_number")
			reference = request_data.get("reference")
			response = self.pesaway.send_mobile_money(amount, currency, recipient_number, reference)
			return JsonResponse(response)
		except Exception as e:
			lgr.exception("Mobile Money Transfer Failed: %s", e)
			return JsonResponse({"code": "999.999.999"}, status=500)
		finally:
			lgr.info("taken %.2f seconds for mobile_money_transfer", time.time() - start)
	
	@csrf_exempt
	def b2b_transfer(self, request):
		start = time.time()
		try:
			data = unpack_request_data(request)
			response = self.pesaway.send_b2b_payment(
				external_reference=data.get("ExternalReference"),
				amount=data.get("Amount"),
				account_number=data.get("AccountNumber"),
				channel=data.get("Channel"),
				reason=data.get("Reason"),
				results_url=data.get("ResultsUrl"),
			)
			return JsonResponse(response)
		except Exception as e:
			lgr.exception("B2B Transfer Failed: %s", e)
			return JsonResponse({"code": "999.999.999"}, status=500)
		finally:
			lgr.info("taken %.2f seconds for b2b_transfer", time.time() - start)
	
	@csrf_exempt
	def b2b_transfer_callback_url(self, request):
		try:
			data = unpack_request_data(request)
			lgr.info("B2B Transfer Callback Data: %s", data)
			return JsonResponse(data)
		except Exception as e:
			lgr.exception("B2B Transfer Failed: %s", e)
			return JsonResponse({"code": "999.999.999"}, status=500)
		finally:
			lgr.info("taken %.2f seconds for b2b_transfer")
	
	@csrf_exempt
	def b2c_transfer(self, request):
		start = time.time()
		try:
			data = unpack_request_data(request)
			reference = TransactionRefGenerator().generate()
			channel = "MPESA"
			reason = f"Withdrawal from contribution on {timezone.now()}"
			ref = str(reference) + str(time.time()).replace('.', '')
			response = self.pesaway.receive_c2b_payment(
				external_reference=ref,
				amount=data.get("amount"),
				phone_number=data.get("phone_number"),
				channel=channel,
				reason=reason,
				results_url="https://zentu.rentwaveafrica.co.ke/billing/wallet/b2c_transfer_callback_url/"
			)
			if response.get('code') != '200.001':
				lgr.error("C2B Transfer Failed: %s", response)
				return JsonResponse({"code": "403.033", "message": "Transaction could not be completed"}, status=500)
			data['ref'] = ref
			payment = InitiatePayment().post(contribution_id=data.get("contribution"), **data)
			return JsonResponse(payment)
		except Exception as e:
			lgr.exception("B2C Transfer Failed: %s", e)
			return JsonResponse({"code": "999.999.999"}, status=500)
		finally:
			lgr.info("taken %.2f seconds for b2c_transfer", time.time() - start)
	
	@csrf_exempt
	def b2c_transfer_callback_url(self, request):
		try:
			data = unpack_request_data(request)
			print("B2C Transfer Callback Data: %s", data)
			if data.get("ResultCode") == 0 and data.get(
					"ResultDesc") == "The service request is processed successfully.":
				reference = data.get("OriginatorReference")
				receipt = data.get("TransactionID")
				approve_transaction = ApprovePaymentTransaction().post(request, reference=reference, receipt=receipt)
				print(approve_transaction)
				return JsonResponse(approve_transaction)
			else:
				return JsonResponse({"code": "999.999.999"}, status=500)
		except Exception as e:
			lgr.exception("B2C Transfer Failed: %s", e)
			return JsonResponse({"code": "999.999.999"}, status=500)
		finally:
			lgr.info("taken %.2f seconds for b2c_transfer")
	
	@csrf_exempt
	def c2b_payment(self, request):
		start = time.time()
		try:
			data = unpack_request_data(request)
			reference = TransactionRefGenerator().generate()
			channel = "MPESA"
			reason = f"Contribution on {timezone.now()}"
			ref = str(reference) + str(time.time()).replace('.', '')
			response = self.pesaway.receive_c2b_payment(
				external_reference=ref,
				amount=data.get("amount"),
				phone_number=data.get("phone_number"),
				channel=channel,
				reason=reason,
				results_url="https://zentu.rentwaveafrica.co.ke/billing/wallet/c2b_payment_callback/"
			)
			if response.get('code') != '200.001':
				lgr.error("C2B Transfer Failed: %s", response)
				return JsonResponse({"code": "403.033", "message":"Transaction could not be completed"}, status=500)
			data['ref'] = ref
			topup = InitiateTopup().post(contribution_id=data.get("contribution"), **data)
			return JsonResponse(topup)
		except Exception as e:
			lgr.exception("C2B Transfer Failed: %s", e)
			return JsonResponse({"code": "999.999.999"}, status=500)
		finally:
			lgr.info("taken %.2f seconds for c2b_payment", time.time() - start)
	
	@csrf_exempt
	def c2b_payment_callback_endpoint(self, request):
		try:
			data = unpack_request_data(request)
			print("C2B Payment Callback Data: %s", data)
			if data.get("ResultCode") == 0 and data.get("ResultDesc") == "The service request is processed successfully.":
				reference = data.get("OriginatorReference")
				receipt = data.get("TransactionID")
				approve_transaction = ApproveTopupTransaction().post(request, reference=reference, receipt=receipt)
				print(approve_transaction)
				return JsonResponse(approve_transaction)
			else:
				return JsonResponse({"code": "999.999.999"}, status=500)
		except Exception as e:
			lgr.exception("C2B Transfer Failed: %s", e)
			return JsonResponse({"code": "999.999.999"}, status=500)
	
	@csrf_exempt
	def authorize_transaction(self, request):
		start = time.time()
		try:
			data = unpack_request_data(request)
			response = self.pesaway.authorize_transaction(
				transaction_id=data.get("TransactionID"),
				otp=data.get("OTP")
			)
			return JsonResponse(response)
		except Exception as e:
			lgr.exception("Authorization Failed: %s", e)
			return JsonResponse({"code": "999.999.999"}, status=500)
		finally:
			lgr.info("taken %.2f seconds for authorize_transaction", time.time() - start)
	
	@csrf_exempt
	def bank_payment(self, request):
		start = time.time()
		try:
			data = unpack_request_data(request)
			response = self.pesaway.send_bank_payment(
				external_reference=data.get("ExternalReference"),
				amount=data.get("Amount"),
				account_number=data.get("AccountNumber"),
				channel=data.get("Channel"),
				bank_code=data.get("BankCode"),
				currency=data.get("Currency"),
				reason=data.get("Reason"),
				results_url=data.get("ResultsUrl"),
			)
			return JsonResponse(response)
		except Exception as e:
			lgr.exception("Bank Payment Failed: %s", e)
			return JsonResponse({"code": "999.999.999"}, status=500)
		finally:
			lgr.info("taken %.2f seconds for bank_payment", time.time() - start)
	
	@csrf_exempt
	def bank_payment_callback_url(self, request):
		start = time.time()
		try:
			data = unpack_request_data(request)
			lgr.info("Bank Payment Callback Data: %s", data)
			return JsonResponse(data)
		except Exception as e:
			lgr.exception("Bank Payment Failed: %s", e)
			return JsonResponse({"code": "999.999.999"}, status=500)
	
	@csrf_exempt
	def query_bank_transaction(self, request):
		start = time.time()
		try:
			data = unpack_request_data(request)
			response = self.pesaway.query_bank_transaction(
				transaction_reference=data.get("TransactionReference")
			)
			return JsonResponse(response)
		except Exception as e:
			lgr.exception("Bank Transaction Query Failed: %s", e)
			return JsonResponse({"code": "999.999.999"}, status=500)
		finally:
			lgr.info("taken %.2f seconds for query_bank_transaction", time.time() - start)
	
	@csrf_exempt
	def query_mobile_money_transaction(self, request):
		start = time.time()
		try:
			data = unpack_request_data(request)
			response = self.pesaway.query_mobile_money_transaction(
				transaction_reference=data.get("TransactionReference")
			)
			return JsonResponse(response)
		except Exception as e:
			lgr.exception("Mobile Money Transaction Query Failed: %s", e)
			return JsonResponse({"code": "999.999.999"}, status=500)
		finally:
			lgr.info("taken %.2f seconds for query_mobile_money_transaction", time.time() - start)
	
	@csrf_exempt
	def pull_transactions(self, request):
		start = time.time()
		try:
			data = unpack_request_data(request)
			start_date = datetime.strptime(data.get("StartDate"), "%Y-%m-%d %H:%M:%S")
			end_date = datetime.strptime(data.get("EndDate"), "%Y-%m-%d %H:%M:%S")
			trans_type = data.get("TransType")
			offset = data.get("OffsetValue", 0)
			response = self.pesaway.pull_mobile_money_transactions(start_date, end_date, trans_type, offset)
			return JsonResponse(response)
		except Exception as e:
			lgr.exception("Pull Transactions Failed: %s", e)
			return JsonResponse({"code": "999.999.999"}, status=500)
		finally:
			lgr.info("taken %.2f seconds for pull_transactions", time.time() - start)
	
	@csrf_exempt
	def send_airtime(self, request):
		start = time.time()
		try:
			data = unpack_request_data(request)
			response = self.pesaway.send_airtime(
				external_reference=data.get("ExternalReference"),
				amount=data.get("Amount"),
				phone_number=data.get("PhoneNumber"),
				reason=data.get("Reason"),
				results_url=data.get("ResultsUrl"),
			)
			return JsonResponse(response)
		except Exception as e:
			lgr.exception("Airtime Response Failed: %s", e)
			return JsonResponse({"code": "999.999.999"}, status=500)
		finally:
			lgr.info("taken %.2f seconds for send_airtime", time.time() - start)

pesaway_interface = PesaWayWalletInterface(
	client_id="4yN4wTqhNDRRKY6oMksGVbTa9Q8xP0px",
	client_secret="S9zRS9Q3f7DBkC7I"
)

urlpatterns = [
	path('wallet/balance/', pesaway_interface.wallet_balance),
	path('wallet/mobile-money-transfer/', pesaway_interface.mobile_money_transfer),
	path('wallet/b2b-transfer/', pesaway_interface.b2b_transfer),
	path('wallet/b2c-transfer/', pesaway_interface.b2c_transfer),
	path('wallet/c2b-payment/', pesaway_interface.c2b_payment),
	path('wallet/authorize-transaction/', pesaway_interface.authorize_transaction),
	path('wallet/bank-payment/', pesaway_interface.bank_payment),
	path('wallet/query-bank-transaction/', pesaway_interface.query_bank_transaction),
	path('wallet/query-mobile-money-transaction/', pesaway_interface.query_mobile_money_transaction),
	path('wallet/pull-transactions/', pesaway_interface.pull_transactions),
	path('wallet/send-airtime/', pesaway_interface.send_airtime),
	
	path('wallet/b2b_transfer_callback_url/', pesaway_interface.b2b_transfer_callback_url),
	path('wallet/b2c_transfer_callback_url/', pesaway_interface.b2c_transfer_callback_url),
	path('wallet/c2b_payment_callback/', pesaway_interface.c2b_payment_callback_endpoint),
	path('wallet/bank_payment_callback_url/', pesaway_interface.bank_payment_callback_url),
]
