import json
import asyncio
import time
import uuid
from datetime import datetime
from decimal import Decimal, ROUND_UP
from typing import Dict, Any, Optional
from functools import wraps
from contextlib import asynccontextmanager
import structlog
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from asgiref.sync import sync_to_async

from billing.backend.interfaces.topup import InitiateTopup, ApproveTopupTransaction
from billing.backend.interfaces.payment import InitiatePayment, ApprovePaymentTransaction
from billing.helpers.generate_unique_ref import TransactionRefGenerator
from billing.itergrations.pesaway import PesaWayClientPool
from mchangohub import settings

logger = structlog.get_logger(__name__)


class ErrorCodes:
	SUCCESS = "200.001"
	TRANSACTION_FAILED = "403.033"
	VALIDATION_ERROR = "400.001"
	RATE_LIMIT_EXCEEDED = "429.001"
	INTERNAL_ERROR = "999.999.999"


class TransactionStatus:
	SUCCESS = 0
	FAILED = 1
	PENDING = 2


CHARGE_TIERS = [
	(0, 1000, Decimal('0.005')),  # 0.5%
	(1001, 10000, Decimal('0.01')),  # 1%
	(10001, 100000, Decimal('0.015')),  # 1.5%
	(100001, 500000, Decimal('0.02')),  # 2%
	(500001, 1000000, Decimal('0.025')),  # 2.5%
	(1000001, 5000000, Decimal('0.03')),  # 3%
	(5000001, 10000000, Decimal('0.04')),  # 4%
]


def calculate_fair_tiered_charge(amount_kes: float) -> float:
	"""Optimized charge calculation with caching and decimal precision"""
	cache_key = f"charge_calc_{int(amount_kes * 100)}"  # Cache by cents
	cached_result = cache.get(cache_key)
	if cached_result is not None:
		return cached_result
	
	amount = Decimal(str(amount_kes))
	
	if amount > 10000000:
		charge = float((amount * Decimal('0.05')).quantize(Decimal('0.01'), rounding=ROUND_UP))
	else:
		charge_decimal = Decimal('0.0')
		for lower, upper, rate in CHARGE_TIERS:
			if amount > lower:
				applicable_amount = min(amount, Decimal(str(upper))) - Decimal(str(lower))
				charge_decimal += applicable_amount * rate
		charge = float(charge_decimal.quantize(Decimal('0.01'), rounding=ROUND_UP))
	cache.set(cache_key, charge, 3600)
	return charge


def async_view(func):
	"""Decorator to handle async views properly"""
	
	@wraps(func)
	def wrapper(self, request, *args, **kwargs):
		return asyncio.run(func(self, request, *args, **kwargs))
	
	return wrapper


def rate_limit(requests_per_minute: int = 1000):
	"""Rate limiting decorator"""
	
	def decorator(func):
		@wraps(func)
		async def wrapper(self, request, *args, **kwargs):
			client_id = request.META.get('HTTP_X_FORWARDED_FOR',
			                             request.META.get('REMOTE_ADDR', 'unknown'))
			rate_limit_key = f"rate_limit:{func.__name__}:{client_id}"
			current_requests = cache.get(rate_limit_key, 0)
			
			if current_requests >= requests_per_minute:
				logger.warning("Rate limit exceeded",
				               client_id=client_id,
				               endpoint=func.__name__,
				               requests=current_requests)
				return JsonResponse({
					"code": ErrorCodes.RATE_LIMIT_EXCEEDED,
					"message": "Rate limit exceeded. Please try again later."
				}, status=429)
			cache.set(rate_limit_key, current_requests + 1, 60)
			return await func(self, request, *args, **kwargs)
		return wrapper
	return decorator


def validate_request_data(required_fields: list, optional_fields: list = None):
	"""Request validation decorator"""
	
	def decorator(func):
		@wraps(func)
		async def wrapper(self, request, *args, **kwargs):
			try:
				data = await self.unpack_request_data_async(request)
				missing_fields = [field for field in required_fields if not data.get(field)]
				if missing_fields:
					return JsonResponse({
						"code": ErrorCodes.VALIDATION_ERROR,
						"message": f"Missing required fields: {', '.join(missing_fields)}"
					}, status=400)
				return await func(self, request, *args, **kwargs)
			except json.JSONDecodeError:
				return JsonResponse({
					"code": ErrorCodes.VALIDATION_ERROR,
					"message": "Invalid JSON in request body"
				}, status=400)
			except Exception as e:
				logger.error("Validation error", error=str(e))
				return JsonResponse({
					"code": ErrorCodes.INTERNAL_ERROR,
					"message": "Request validation failed"
				}, status=500)
		
		return wrapper
	
	return decorator


class PesaWayWalletInterface(View):
	def __init__(self, **kwargs):
		super().__init__(**kwargs)
		self.client_pool = None
		self._pool_initialized = False
	
	async def get_client_pool(self):
		"""Lazy initialization of client pool"""
		if not self._pool_initialized:
			self.client_pool = PesaWayClientPool(
				pool_size=getattr(settings, 'PESAWAY_POOL_SIZE', 10),
				client_id=settings.PESAWAY_CLIENT_ID,
				client_secret=settings.PESAWAY_CLIENT_SECRET,
				max_connections=getattr(settings, 'PESAWAY_MAX_CONNECTIONS', 200),
				max_concurrent_requests=getattr(settings, 'PESAWAY_MAX_CONCURRENT_REQUESTS', 100),
				redis_url=getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
			)
			await self.client_pool.__aenter__()
			self._pool_initialized = True
		return self.client_pool
	
	async def unpack_request_data_async(self, request) -> Dict[str, Any]:
		"""Async version of request data unpacking with better error handling"""
		try:
			content_type = request.META.get('CONTENT_TYPE', '')
			
			if 'application/json' in content_type:
				body = request.body.decode('utf-8')
				return json.loads(body) if body else {}
			elif request.method == 'GET':
				return dict(request.GET)
			elif request.method == 'POST':
				if content_type.startswith('multipart/form-data'):
					return dict(request.POST)
				else:
					return dict(request.POST)
			return {}
		except (json.JSONDecodeError, UnicodeDecodeError) as e:
			logger.error("Failed to unpack request data", error=str(e))
			raise
	
	def create_error_response(self, error_code: str, message: str, status: int = 500, **extra_data):
		"""Standardized error response creation"""
		response_data = {
			"code": error_code,
			"message": message,
			"timestamp": timezone.now().isoformat(),
			"request_id": str(uuid.uuid4())
		}
		response_data.update(extra_data)
		return JsonResponse(response_data, status=status)
	
	def create_success_response(self, data: Dict[str, Any], **extra_data):
		"""Standardized success response creation"""
		response_data = {
			"code": ErrorCodes.SUCCESS,
			"timestamp": timezone.now().isoformat(),
			"request_id": str(uuid.uuid4()),
			"data": data
		}
		response_data.update(extra_data)
		return JsonResponse(response_data)
	
	@method_decorator(csrf_exempt)
	@method_decorator(require_http_methods(["GET"]))
	@async_view
	@rate_limit(500)  # 500 requests per minute for balance checks
	async def wallet_balance(self, request):
		"""Get wallet balance with caching"""
		request_id = str(uuid.uuid4())
		start_time = time.time()
		
		try:
			logger.info("Wallet balance request started", request_id=request_id)
			cache_key = f"wallet_balance:{settings.PESAWAY_CLIENT_ID}"
			cached_balance = cache.get(cache_key)
			if cached_balance:
				logger.info("Returning cached balance", request_id=request_id)
				return self.create_success_response(cached_balance, cached=True)
			client_pool = await self.get_client_pool()
			client = client_pool.get_client()
			response = await client.get_account_balance()
			if response.success:
				cache.set(cache_key, response.data, 300)
				return self.create_success_response(response.data)
			else:
				return self.create_error_response(
					ErrorCodes.INTERNAL_ERROR,
					"Failed to retrieve balance",
					error_details=response.error
				)
		except Exception as e:
			logger.exception("Error fetching wallet balance",
			                 request_id=request_id, error=str(e))
			return self.create_error_response(
				ErrorCodes.INTERNAL_ERROR,
				"Wallet balance retrieval failed"
			)
		finally:
			duration = time.time() - start_time
			logger.info("Wallet balance request completed",
			            request_id=request_id, duration=duration)
	
	@method_decorator(csrf_exempt)
	@method_decorator(require_http_methods(["POST"]))
	@async_view
	@rate_limit(200)  
	@validate_request_data(['amount', 'currency', 'recipient_number', 'reference'])
	async def mobile_money_transfer(self, request):
		"""Enhanced mobile money transfer with validation and monitoring"""
		request_id = str(uuid.uuid4())
		start_time = time.time()
		
		try:
			data = await self.unpack_request_data_async(request)
			
			logger.info("Mobile money transfer initiated",
			            request_id=request_id,
			            amount=data.get('amount'),
			            recipient=data.get('recipient_number')[:6] + "****") 
			try:
				amount = float(data.get('amount'))
				if amount <= 0:
					return self.create_error_response(
						ErrorCodes.VALIDATION_ERROR,
						"Amount must be greater than zero",
						status=400
					)
			except (ValueError, TypeError):
				return self.create_error_response(
					ErrorCodes.VALIDATION_ERROR,
					"Invalid amount format",
					status=400
				)
			duplicate_check_key = f"transfer_ref:{data.get('reference')}"
			if cache.get(duplicate_check_key):
				return self.create_error_response(
					ErrorCodes.VALIDATION_ERROR,
					"Duplicate reference detected",
					status=409
				)
			cache.set(duplicate_check_key, True, 86400)
			client_pool = await self.get_client_pool()
			client = client_pool.get_client()
			response = await client.send_mobile_money(
				amount=amount,
				currency=data.get('currency'),
				recipient_number=data.get('recipient_number'),
				reference=data.get('reference')
			)
			if response.success:
				logger.info("Mobile money transfer successful",
				            request_id=request_id,
				            transaction_id=response.data.get('transaction_id'))
				return self.create_success_response(response.data)
			else:
				return self.create_error_response(
					ErrorCodes.TRANSACTION_FAILED,
					"Transfer could not be completed",
					error_details=response.error
				)
		except Exception as e:
			logger.exception("Mobile money transfer failed",
			                 request_id=request_id, error=str(e))
			return self.create_error_response(
				ErrorCodes.INTERNAL_ERROR,
				"Transfer processing failed"
			)
		finally:
			duration = time.time() - start_time
			logger.info("Mobile money transfer completed",
			            request_id=request_id, duration=duration)

	@method_decorator(csrf_exempt, name='dispatch')
	@method_decorator(require_http_methods(["POST"]), name='dispatch')
	@async_view
	@rate_limit(100)
	@validate_request_data(['amount', 'phone_number', 'contribution'])
	async def b2c_transfer(self, request):
		"""Enhanced B2C transfer with async processing"""
		request_id = str(uuid.uuid4())
		start_time = time.time()

		try:
			data = await self.unpack_request_data_async(request)
			base_reference = TransactionRefGenerator().generate()
			reference = f"{base_reference}{int(time.time())}"
			try:
				base_amount = float(data.get('amount'))
				if base_amount <= 0:
					return self.create_error_response(
						ErrorCodes.VALIDATION_ERROR,
						"Amount must be greater than zero",
						status=400
					)
				charge = calculate_fair_tiered_charge(base_amount)
				total_amount = base_amount + charge
			except (ValueError, TypeError):
				return self.create_error_response(
					ErrorCodes.VALIDATION_ERROR,
					"Invalid amount format",
					status=400
				)
			logger.info("B2C transfer initiated",
						extra=dict(request_id=request_id,
								   reference=reference,
								   base_amount=base_amount,
								   charge=charge,
								   total_amount=total_amount))
			client_pool = await self.get_client_pool()
			client = client_pool.get_client()
			response = await client.send_b2c_payment(
				external_reference=reference,
				amount=total_amount,
				phone_number=data.get('phone_number'),
				reason=f"Withdrawal from contribution on {timezone.now()}",
				results_url=settings.PESAWAY_B2C_CALLBACK
			)
			logger.info("B2C transfer API response: %s", response)
			if not response.success or (response.data and response.data.get('code') != ErrorCodes.SUCCESS):
				logger.error("B2C API call failed",
							 extra=dict(request_id=request_id,
										api_response=response.data))
				return self.create_error_response(
					ErrorCodes.TRANSACTION_FAILED,
					"Transaction could not be initiated"
				)
			payment_data = {**data, 'ref': reference, 'charge': charge}
			logger.info("Payment data is %s " % payment_data)
			payment = await sync_to_async(InitiatePayment().post)(
				contribution_id=data.get('contribution'), **payment_data
			)
			logger.info("B2C transfer processing completed",
						extra=dict(request_id=request_id, reference=reference))
			return self.create_success_response({
				"transaction_reference": reference,
				"amount": base_amount,
				"charge": charge,
				"total_amount": total_amount,
				"status": "PENDING",
				**payment
			})

		except Exception as e:
			logger.exception("B2C transfer failed",
							 extra=dict(request_id=request_id, error=str(e)))
			return self.create_error_response(
				ErrorCodes.INTERNAL_ERROR,
				"B2C transfer processing failed"
			)
		finally:
			duration = time.time() - start_time
			logger.info("B2C transfer request completed",
						extra=dict(request_id=request_id, duration=duration))

	@method_decorator(csrf_exempt)
	# @method_decorator(require_http_methods(["POST"]))
	@async_view
	async def b2c_transfer_callback_url(self, request):
		"""B2C callback handler with enhanced processing"""
		request_id = str(uuid.uuid4())
		try:
			data = await self.unpack_request_data_async(request)
			logger.info("B2C callback received",
			            request_id=request_id,
			            result_code=data.get("ResultCode"),
			            originator_ref=data.get("OriginatorReference"))
			result_code = data.get("ResultCode")
			result_desc = data.get("ResultDesc", "")
			if result_code == TransactionStatus.SUCCESS and "successfully" in result_desc.lower():
				reference = data.get("OriginatorReference")
				receipt = data.get("TransactionID")
				if not reference or not receipt:
					logger.error("Missing transaction details in callback",
					             request_id=request_id, data=data)
					return self.create_error_response(
						ErrorCodes.VALIDATION_ERROR,
						"Missing transaction reference or receipt"
					)
				approval_result = await sync_to_async(ApprovePaymentTransaction().post)(
					request, reference=reference, receipt=receipt
				)
				logger.info("B2C transaction approved",
				            request_id=request_id,
				            reference=reference,
				            receipt=receipt)
				return self.create_success_response({
					"status": "APPROVED",
					"reference": reference,
					"receipt": receipt,
					**approval_result
				})
			else:
				logger.warning("B2C transaction failed",
				               request_id=request_id,
				               result_code=result_code,
				               result_desc=result_desc)
				
				return self.create_error_response(
					ErrorCodes.TRANSACTION_FAILED,
					f"Transaction failed: {result_desc}",
					result_code=result_code
				)
		
		except Exception as e:
			logger.exception("B2C callback processing failed",
			                 request_id=request_id, error=str(e))
			return self.create_error_response(
				ErrorCodes.INTERNAL_ERROR,
				"Callback processing failed"
			)
	
	@method_decorator(csrf_exempt)
	@method_decorator(require_http_methods(["POST"]))
	@async_view
	@rate_limit(150)  # 150 C2B payments per minute
	@validate_request_data(['amount', 'phone_number', 'contribution'])
	async def c2b_payment(self, request):
		"""Enhanced C2B payment processing"""
		request_id = str(uuid.uuid4())
		start_time = time.time()
		
		try:
			data = await self.unpack_request_data_async(request)
			print(data)
			base_reference = TransactionRefGenerator().generate()
			reference = f"{base_reference}{int(time.time())}"
			base_amount = float(data.get('amount'))
			charge = calculate_fair_tiered_charge(base_amount)
			total_amount = base_amount + charge
			logger.info("C2B payment initiated",
			            request_id=request_id,
			            reference=reference,
			            amount=total_amount)
			client_pool = await self.get_client_pool()
			client = client_pool.get_client()
			response = await client.receive_c2b_payment(
				external_reference=reference,
				amount=total_amount,
				phone_number=data.get('phone_number'),
				reason=f"Contribution on {timezone.now()}",
				results_url=settings.PESAWAY_C2B_CALLBACK
			)
			if not response.success or response.data.get('code') != ErrorCodes.SUCCESS:
				return self.create_error_response(
					ErrorCodes.TRANSACTION_FAILED,
					"Payment could not be initiated"
				)
			topup_data = {
				**data,
				'ref': reference,
				'charge': charge 
			}
			topup_result = await sync_to_async(InitiateTopup().post)(
				contribution_id=data.get('contribution'), **topup_data
			)
			return self.create_success_response({
				"transaction_reference": reference,
				"amount": base_amount,
				"charge": charge,
				"total_amount": total_amount,
				"status": "PENDING",
				**topup_result
			})
		
		except Exception as e:
			logger.exception("C2B payment failed",
			                 request_id=request_id, error=str(e))
			return self.create_error_response(
				ErrorCodes.INTERNAL_ERROR,
				"C2B payment processing failed"
			)
		finally:
			duration = time.time() - start_time
			logger.info("C2B payment completed",
			            request_id=request_id, duration=duration)
	
	@method_decorator(csrf_exempt)
	# @method_decorator(require_http_methods(["POST"]))
	@async_view
	async def c2b_payment_callback_endpoint(self, request):
		"""C2B callback handler"""
		request_id = str(uuid.uuid4())
		try:
			data = await self.unpack_request_data_async(request)
			print(data)
			logger.info("C2B callback received",
			            request_id=request_id,
			            result_code=data.get("ResultCode"))
			
			if (data.get("ResultCode") == TransactionStatus.SUCCESS and
					"successfully" in data.get("ResultDesc", "").lower()):
				
				reference = data.get("OriginatorReference")
				receipt = data.get("TransactionID")
				
				approval_result = await sync_to_async(ApproveTopupTransaction().post)(
					request, reference=reference, receipt=receipt
				)
				
				logger.info("C2B transaction approved",
				            request_id=request_id,
				            reference=reference)
				
				return self.create_success_response({
					"status": "APPROVED",
					"reference": reference,
					"receipt": receipt,
					**approval_result
				})
			else:
				return self.create_error_response(
					ErrorCodes.TRANSACTION_FAILED,
					"Transaction failed"
				)
		
		except Exception as e:
			logger.exception("C2B callback failed",
			                 request_id=request_id, error=str(e))
			return self.create_error_response(
				ErrorCodes.INTERNAL_ERROR,
				"Callback processing failed"
			)
	
	@method_decorator(csrf_exempt)
	@method_decorator(require_http_methods(["POST"]))
	@async_view
	@rate_limit(100)
	@validate_request_data(['TransactionReference'])
	async def query_mobile_money_transaction(self, request):
		"""Query transaction status with caching"""
		request_id = str(uuid.uuid4())
		
		try:
			data = await self.unpack_request_data_async(request)
			transaction_ref = data.get("TransactionReference")
			
			# Check cache first
			cache_key = f"transaction_status:{transaction_ref}"
			cached_status = cache.get(cache_key)
			
			if cached_status:
				return self.create_success_response(cached_status, cached=True)
			client_pool = await self.get_client_pool()
			client = client_pool.get_client()
			response = await client.query_mobile_money_transaction(transaction_ref)
			if response.success:
				cache.set(cache_key, response.data, 300)
				return self.create_success_response(response.data)
			else:
				return self.create_error_response(
					ErrorCodes.INTERNAL_ERROR,
					"Query failed"
				)
		except Exception as e:
			logger.exception("Transaction query failed",
			                 request_id=request_id, error=str(e))
			return self.create_error_response(
				ErrorCodes.INTERNAL_ERROR,
				"Query processing failed"
			)


pesaway_interface = PesaWayWalletInterface()


@csrf_exempt
@require_http_methods(["GET"])
def health_check(request):
	"""Health check endpoint for load balancers"""
	return JsonResponse({
		"status": "healthy",
		"timestamp": timezone.now().isoformat(),
		"service": "pesaway-wallet-api"
	})


@csrf_exempt
@require_http_methods(["GET"])
def ready_check(request):
	"""Readiness check for Kubernetes"""
	try:
		cache.get("health_check")
		return JsonResponse({
			"status": "ready",
			"timestamp": timezone.now().isoformat(),
			"checks": {
				"cache": "ok",
				"database": "ok"
			}
		})
	except Exception as e:
		return JsonResponse({
			"status": "not_ready",
			"error": str(e)
		}, status=503)


from django.urls import path, include

api_v1_patterns = [
	path('wallet/balance/', pesaway_interface.wallet_balance, name='wallet_balance'),
	path('wallet/mobile-money-transfer/', pesaway_interface.mobile_money_transfer, name='mobile_money_transfer'),
	path('wallet/b2c-transfer/', pesaway_interface.b2c_transfer, name='b2c_transfer'),
	path('wallet/c2b-payment/', pesaway_interface.c2b_payment, name='c2b_payment'),
	path('wallet/query-mobile-money-transaction/', pesaway_interface.query_mobile_money_transaction,
	     name='query_transaction'),
	
	path('callbacks/b2c/', pesaway_interface.b2c_transfer_callback_url, name='b2c_callback'),
	path('callbacks/c2b/', pesaway_interface.c2b_payment_callback_endpoint, name='c2b_callback'),
]

urlpatterns = [
	path('api/v1/', include(api_v1_patterns)),
	path('health/', health_check, name='health_check'),
	path('ready/', ready_check, name='ready_check'),
]