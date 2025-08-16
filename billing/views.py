import json
import time
import uuid
from datetime import datetime
from decimal import Decimal, ROUND_UP
from typing import Dict, Any, Optional
from functools import wraps

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from billing.backend.interfaces.topup import InitiateTopup, ApproveTopupTransaction
from billing.backend.interfaces.payment import InitiatePayment, ApprovePaymentTransaction
from billing.helpers.generate_unique_ref import TransactionRefGenerator

import logging

from billing.itergrations.pesaway import PesaWayAPIClient

logger = logging.getLogger(__name__)


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
    """Calculate charge with decimal precision"""
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

    return charge


def rate_limit(requests_per_minute: int = 1000):
    """Simple rate limiting decorator"""

    def decorator(func):
        @wraps(func)
        def wrapper(self, request, *args, **kwargs):
            client_id = request.META.get('HTTP_X_FORWARDED_FOR',
                                         request.META.get('REMOTE_ADDR', 'unknown'))
            rate_limit_key = f"rate_limit:{func.__name__}:{client_id}"
            current_requests = cache.get(rate_limit_key, 0)

            if current_requests >= requests_per_minute:
                logger.warning(f"Rate limit exceeded for {client_id}")
                return JsonResponse({
                    "code": ErrorCodes.RATE_LIMIT_EXCEEDED,
                    "message": "Rate limit exceeded. Please try again later."
                }, status=429)

            cache.set(rate_limit_key, current_requests + 1, 60)
            return func(self, request, *args, **kwargs)

        return wrapper

    return decorator


def validate_request_data(required_fields: list):
    """Request validation decorator"""

    def decorator(func):
        @wraps(func)
        def wrapper(self, request, *args, **kwargs):
            try:
                data = self.unpack_request_data(request)
                missing_fields = [field for field in required_fields if not data.get(field)]
                if missing_fields:
                    return JsonResponse({
                        "code": ErrorCodes.VALIDATION_ERROR,
                        "message": f"Missing required fields: {', '.join(missing_fields)}"
                    }, status=400)
                return func(self, request, *args, **kwargs)
            except json.JSONDecodeError:
                return JsonResponse({
                    "code": ErrorCodes.VALIDATION_ERROR,
                    "message": "Invalid JSON in request body"
                }, status=400)
            except Exception as e:
                logger.error(f"Validation error: {str(e)}")
                return JsonResponse({
                    "code": ErrorCodes.INTERNAL_ERROR,
                    "message": "Request validation failed"
                }, status=500)

        return wrapper

    return decorator


class PesaWayWalletInterface(View):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.client = PesaWayAPIClient(
            client_id=settings.PESAWAY_CLIENT_ID,
            client_secret=settings.PESAWAY_CLIENT_SECRET,
            base_url=getattr(settings, 'PESAWAY_BASE_URL', 'https://api.pesaway.com'),
            timeout=getattr(settings, 'PESAWAY_TIMEOUT', 30)
        )

    def unpack_request_data(self, request) -> Dict[str, Any]:
        """Extract data from request"""
        try:
            content_type = request.META.get('CONTENT_TYPE', '')

            if 'application/json' in content_type:
                body = request.body.decode('utf-8')
                return json.loads(body) if body else {}
            elif request.method == 'GET':
                return dict(request.GET)
            elif request.method == 'POST':
                return dict(request.POST)
            return {}
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Failed to unpack request data: {str(e)}")
            raise

    def create_error_response(self, error_code: str, message: str, status: int = 500, **extra_data):
        """Create standardized error response"""
        response_data = {
            "code": error_code,
            "message": message,
            "timestamp": timezone.now().isoformat(),
            "request_id": str(uuid.uuid4())
        }
        response_data.update(extra_data)
        return JsonResponse(response_data, status=status)

    def create_success_response(self, data: Dict[str, Any], **extra_data):
        """Create standardized success response"""
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
    @rate_limit(500)
    def wallet_balance(self, request):
        """Get wallet balance"""
        request_id = str(uuid.uuid4())
        start_time = time.time()

        try:
            logger.info(f"Wallet balance request started: {request_id}")
            response = self.client.get_account_balance()
            if response.success:
                return self.create_success_response(response.data)
            else:
                return self.create_error_response(
                    ErrorCodes.INTERNAL_ERROR,
                    "Failed to retrieve balance",
                    error_details=response.error
                )
        except Exception as e:
            logger.exception(f"Error fetching wallet balance: {request_id} - {str(e)}")
            return self.create_error_response(
                ErrorCodes.INTERNAL_ERROR,
                "Wallet balance retrieval failed"
            )
        finally:
            duration = time.time() - start_time
            logger.info(f"Wallet balance request completed: {request_id} - {duration}s")

    @method_decorator(csrf_exempt)
    @method_decorator(require_http_methods(["POST"]))
    @rate_limit(200)
    @validate_request_data(['amount', 'currency', 'recipient_number', 'reference'])
    def mobile_money_transfer(self, request):
        """Mobile money transfer"""
        request_id = str(uuid.uuid4())
        start_time = time.time()

        try:
            data = self.unpack_request_data(request)
            logger.info(f"Mobile money transfer initiated: {request_id}")
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

            if not data.get('reference'):
                return self.create_error_response(
                    ErrorCodes.VALIDATION_ERROR,
                    "Reference is required",
                    status=400
                )
            response = self.client.send_mobile_money(
                amount=amount,
                currency=data.get('currency'),
                recipient_number=data.get('recipient_number'),
                reference=data.get('reference')
            )

            if response.success:
                logger.info(f"Mobile money transfer successful: {request_id}")
                return self.create_success_response(response.data)
            else:
                return self.create_error_response(
                    ErrorCodes.TRANSACTION_FAILED,
                    "Transfer could not be completed",
                    error_details=response.error
                )
        except Exception as e:
            logger.exception(f"Mobile money transfer failed: {request_id} - {str(e)}")
            return self.create_error_response(
                ErrorCodes.INTERNAL_ERROR,
                "Transfer processing failed"
            )
        finally:
            duration = time.time() - start_time
            logger.info(f"Mobile money transfer completed: {request_id} - {duration}s")

    @method_decorator(csrf_exempt)
    @method_decorator(require_http_methods(["POST"]))
    @rate_limit(100)
    @validate_request_data(['amount', 'phone_number', 'contribution'])
    def b2c_transfer(self, request):
        """B2C transfer (business to customer)"""
        request_id = str(uuid.uuid4())
        start_time = time.time()
        try:
            data = self.unpack_request_data(request)
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

            logger.info(f"B2C transfer initiated: {request_id} - {reference} - {total_amount}")
            response = self.client.send_b2c_payment(
                external_reference=reference,
                amount=total_amount,
                phone_number=data.get('phone_number'),
                reason=f"Withdrawal from contribution on {timezone.now()}",
                results_url=settings.PESAWAY_B2C_CALLBACK
            )

            if not response.success or (response.data and response.data.get('code') != ErrorCodes.SUCCESS):
                logger.error(f"B2C API call failed: {request_id}")
                return self.create_error_response(
                    ErrorCodes.TRANSACTION_FAILED,
                    "Transaction could not be initiated"
                )
            payment_data = {**data, 'ref': reference, 'charge': charge}
            payment = InitiatePayment().post(
                contribution_id=data.get('contribution'), **payment_data
            )
            logger.info(f"B2C transfer processing completed: {request_id}")
            return self.create_success_response({
                "transaction_reference": reference,
                "amount": base_amount,
                "charge": charge,
                "total_amount": total_amount,
                "status": "PENDING",
                **payment
            })

        except Exception as e:
            logger.exception(f"B2C transfer failed: {request_id} - {str(e)}")
            return self.create_error_response(
                ErrorCodes.INTERNAL_ERROR,
                "B2C transfer processing failed"
            )
        finally:
            duration = time.time() - start_time
            logger.info(f"B2C transfer request completed: {request_id} - {duration}s")

    @method_decorator(csrf_exempt)
    def b2c_transfer_callback_url(self, request):
        """B2C callback handler"""
        request_id = str(uuid.uuid4())
        try:
            data = self.unpack_request_data(request)
            print(data)
            logger.info(f"B2C callback received: {request_id}")
            result_code = data.get("ResultCode")
            result_desc = data.get("ResultDesc", "")
            if result_code == TransactionStatus.SUCCESS and "successfully" in result_desc.lower():
                reference = data.get("OriginatorReference")
                receipt = data.get("TransactionID")
                if not reference or not receipt:
                    logger.error(f"Missing transaction details in callback: {request_id}")
                    return self.create_error_response(
                        ErrorCodes.VALIDATION_ERROR,
                        "Missing transaction reference or receipt"
                    )
                approval_result = ApprovePaymentTransaction().post(
                    request, reference=reference, receipt=receipt
                )
                logger.info(f"B2C transaction approved: {request_id}")
                return self.create_success_response({
                    "status": "APPROVED",
                    "reference": reference,
                    "receipt": receipt,
                    **approval_result
                })
            else:
                logger.warning(f"B2C transaction failed: {request_id} - {result_desc}")
                return self.create_error_response(
                    ErrorCodes.TRANSACTION_FAILED,
                    f"Transaction failed: {result_desc}",
                    result_code=result_code
                )

        except Exception as e:
            logger.exception(f"B2C callback processing failed: {request_id} - {str(e)}")
            return self.create_error_response(
                ErrorCodes.INTERNAL_ERROR,
                "Callback processing failed"
            )

    @method_decorator(csrf_exempt)
    @method_decorator(require_http_methods(["POST"]))
    @rate_limit(150)
    @validate_request_data(['amount', 'phone_number', 'contribution'])
    def c2b_payment(self, request):
        """C2B payment (customer to business)"""
        request_id = str(uuid.uuid4())
        start_time = time.time()
        try:
            data = self.unpack_request_data(request)
            print(data)
            base_reference = TransactionRefGenerator().generate()
            reference = f"{base_reference}{int(time.time())}"
            base_amount = float(data.get('amount'))
            charge = calculate_fair_tiered_charge(base_amount)
            total_amount = base_amount + charge
            logger.info(f"C2B payment initiated: {request_id} - {reference}")
            response = self.client.receive_c2b_payment(
                external_reference=reference,
                amount=total_amount,
                phone_number=data.get('phone_number'),
                reason=f"Contribution on {timezone.now()}",
                results_url=settings.PESAWAY_C2B_CALLBACK
            )
            print(response)
            if not response.success or response.data.get('code') != ErrorCodes.SUCCESS:
                return self.create_error_response(
                    ErrorCodes.TRANSACTION_FAILED,
                    "Payment could not be initiated"
                )
            topup_data = {**data, 'ref': reference, 'charge': charge}
            topup_result = InitiateTopup().post(
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
            logger.exception(f"C2B payment failed: {request_id} - {str(e)}")
            return self.create_error_response(
                ErrorCodes.INTERNAL_ERROR,
                "C2B payment processing failed"
            )
        finally:
            duration = time.time() - start_time
            logger.info(f"C2B payment completed: {request_id} - {duration}s")

    @method_decorator(csrf_exempt)
    def c2b_payment_callback_endpoint(self, request):
        """C2B callback handler"""
        request_id = str(uuid.uuid4())
        try:
            data = self.unpack_request_data(request)
            logger.info(f"C2B callback received: {request_id}")
            if (data.get("ResultCode") == TransactionStatus.SUCCESS and
                    "successfully" in data.get("ResultDesc", "").lower()):

                reference = data.get("OriginatorReference")
                receipt = data.get("TransactionID")

                # Approve transaction
                approval_result = ApproveTopupTransaction().post(
                    request, reference=reference, receipt=receipt
                )

                logger.info(f"C2B transaction approved: {request_id}")
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
            logger.exception(f"C2B callback failed: {request_id} - {str(e)}")
            return self.create_error_response(
                ErrorCodes.INTERNAL_ERROR,
                "Callback processing failed"
            )

    @method_decorator(csrf_exempt)
    @method_decorator(require_http_methods(["POST"]))
    @rate_limit(100)
    @validate_request_data(['TransactionReference'])
    def query_mobile_money_transaction(self, request):
        """Query transaction status"""
        request_id = str(uuid.uuid4())

        try:
            data = self.unpack_request_data(request)
            transaction_ref = data.get("TransactionReference")
            response = self.client.query_mobile_money_transaction(transaction_ref)
            if response.success:
                return self.create_success_response(response.data)
            else:
                return self.create_error_response(
                    ErrorCodes.INTERNAL_ERROR,
                    "Query failed"
                )
        except Exception as e:
            logger.exception(f"Transaction query failed: {request_id} - {str(e)}")
            return self.create_error_response(
                ErrorCodes.INTERNAL_ERROR,
                "Query processing failed"
            )


pesaway_interface = PesaWayWalletInterface()


@csrf_exempt
@require_http_methods(["GET"])
def health_check(request):
    """Health check endpoint"""
    return JsonResponse({
        "status": "healthy",
        "timestamp": timezone.now().isoformat(),
        "service": "pesaway-wallet-api"
    })


@csrf_exempt
@require_http_methods(["GET"])
def ready_check(request):
    """Readiness check endpoint"""
    return JsonResponse({
        "status": "ready",
        "timestamp": timezone.now().isoformat()
    })


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