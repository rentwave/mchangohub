import json
import asyncio
import logging
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import aiohttp
import redis.asyncio as redis
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from prometheus_client import Counter, Histogram, Gauge
import structlog

from mchangohub import settings

API_REQUESTS_TOTAL = Counter('pesaway_api_requests_total', 'Total API requests', ['method', 'endpoint', 'status'])
API_REQUEST_DURATION = Histogram('pesaway_api_request_duration_seconds', 'API request duration', ['method', 'endpoint'])
ACTIVE_CONNECTIONS = Gauge('pesaway_active_connections', 'Active connections')
CIRCUIT_BREAKER_STATE = Gauge('pesaway_circuit_breaker_state', 'Circuit breaker state', ['endpoint'])

logger = structlog.get_logger()


class PaymentChannel(Enum):
    MPESA = "MPESA"
    AIRTEL = "AIRTEL"
    TIGO = "TIGO"
    EQUITY = "EQUITY"
    KCB = "KCB"


class TransactionType(Enum):
    B2B = "B2B"
    B2C = "B2C"
    C2B = "C2B"


@dataclass
class APIResponse:
    success: bool
    data: Optional[Dict[Any, Any]] = None
    error: Optional[str] = None
    status_code: Optional[int] = None
    response_time: Optional[float] = None
    request_id: Optional[str] = None


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open"""
    pass


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
        self._lock = asyncio.Lock()

    async def call(self, func, *args, **kwargs):
        async with self._lock:  # ensure consistent state updates
            if self.state == 'OPEN':
                if (time.time() - self.last_failure_time) > self.timeout:
                    self.state = 'HALF_OPEN'
                    logger.info("Circuit breaker moving to HALF_OPEN state")
                else:
                    raise CircuitBreakerError("Circuit breaker is OPEN")

        try:
            result = await func(*args, **kwargs)
        except Exception as e:
            async with self._lock:
                self.record_failure()
                # If failure happens in HALF_OPEN → immediately OPEN again
                if self.state == "HALF_OPEN":
                    self.state = "OPEN"
                    self.last_failure_time = time.time()
                    logger.warning("Circuit breaker returned to OPEN state after HALF_OPEN failure")
            raise e

        async with self._lock:
            if self.state == 'HALF_OPEN':
                self.reset()
        return result

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = 'OPEN'
            logger.warning(f"Circuit breaker opened after {self.failure_count} failures")

    def reset(self):
        self.failure_count = 0
        self.state = 'CLOSED'
        self.last_failure_time = None
        logger.info("Circuit breaker reset to CLOSED state")


class TokenManager:
    def __init__(self, redis_client: redis.Redis, client_id: str, client_secret: str):
        self.redis_client = redis_client
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_key = f"pesaway_token:{client_id}"

    async def get_token(self) -> Optional[str]:
        try:
            token_data = await self.redis_client.get(self.token_key)  # ✅ async get
            if token_data:
                return json.loads(token_data)['token']
        except Exception as e:
            logger.error("Failed to get token from cache", error=str(e))
        return None

    async def set_token(self, token: str, expires_in: int = 3600):
        try:
            token_data = {
                'token': token,
                'expires_at': time.time() + expires_in - 300
            }
            await self.redis_client.setex(  # ✅ async setex
                self.token_key,
                expires_in - 300,
                json.dumps(token_data)
            )
        except Exception as e:
            logger.error("Failed to cache token", error=str(e))


class PesaWayAPIClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        base_url: str = settings.PESAWAY_BASE_URL,
        redis_url: str = settings.REDIS_URL,
        max_connections: int = 100,
        max_concurrent_requests: int = 50,
        timeout: int = 30,
        max_retries: int = 3
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url.rstrip("/")
        self.max_concurrent_requests = max_concurrent_requests
        self.timeout = timeout
        self.max_retries = max_retries
        self.redis_client = redis.from_url(redis_url, decode_responses=True)

        self.token_manager = TokenManager(
            self.redis_client, client_id, client_secret
        )

        self.connector = aiohttp.TCPConnector(
            limit=max_connections,
            limit_per_host=max_connections,
            keepalive_timeout=60,
            enable_cleanup_closed=True,
        )
        self.semaphore = asyncio.Semaphore(max_concurrent_requests)
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(
            connector=self.connector,
            timeout=aiohttp.ClientTimeout(total=self.timeout),
            headers={"User-Agent": "PesaWay-Client/2.0"},
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()
            self._session = None

    def get_circuit_breaker(self, endpoint: str) -> CircuitBreaker:
        if endpoint not in self.circuit_breakers:
            self.circuit_breakers[endpoint] = CircuitBreaker()
        return self.circuit_breakers[endpoint]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
    )
    async def _authenticate(self) -> str:
        url = f"{self.base_url}/api/v1/token/"
        payload = {
            "consumer_key": self.client_id,
            "consumer_secret": self.client_secret,
            "grant_type": "client_credentials",
        }
        async with self._session.post(url, json=payload) as response:
            response.raise_for_status()
            data = await response.json()
            token = data["data"]["token"]
            expires_in = data.get("data", {}).get("expires_in", 3600)
            await self.token_manager.set_token(token, expires_in)
            return token

    async def _get_headers(self) -> Dict[str, str]:
        token = await self.token_manager.get_token()
        if not token:
            token = await self._authenticate()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Request-ID": f"{int(time.time())}-{id(asyncio.current_task())}",
        }

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[Dict] = None,
        retries: int = 0,
    ):
        start_time = time.time()
        request_id = f"{int(start_time)}-{id(asyncio.current_task())}"
        rate_limit_key = f"rate_limit:{self.client_id}"
        current_requests = await self.redis_client.incr(rate_limit_key)
        if current_requests == 1:
            await self.redis_client.expire(rate_limit_key, 60)
        if current_requests > settings.PESAWAY_RATE_LIMIT_PER_MINUTE:
            return APIResponse(
                False,
                error="Rate limit exceeded",
                status_code=429,
                request_id=request_id,
            )
        circuit_breaker = self.get_circuit_breaker(endpoint)
        async with self.semaphore:
            ACTIVE_CONNECTIONS.inc()
            try:
                headers = await self._get_headers()
                url = f"{self.base_url}{endpoint}"

                async def make_http_request():
                    if method.upper() == "GET":
                        return await self._session.get(url, headers=headers)
                    else:
                        return await self._session.post(
                            url, json=payload, headers=headers
                        )
                response = await circuit_breaker.call(make_http_request)
                response_time = time.time() - start_time
                if response.status == 401 and retries < 1:
                    await self._authenticate()
                    return await self._make_request(
                        method, endpoint, payload, retries + 1
                    )
                response.raise_for_status()
                data = await response.json()
                API_REQUESTS_TOTAL.labels(
                    method=method, endpoint=endpoint, status="success"
                ).inc()
                API_REQUEST_DURATION.labels(
                    method=method, endpoint=endpoint
                ).observe(response_time)

                return APIResponse(
                    True,
                    data=data,
                    status_code=response.status,
                    response_time=response_time,
                    request_id=request_id,
                )

            except CircuitBreakerError:
                return APIResponse(
                    False,
                    error="Service temporarily unavailable",
                    status_code=503,
                    request_id=request_id,
                )

            except aiohttp.ClientResponseError as e:
                circuit_breaker.record_failure()
                API_REQUESTS_TOTAL.labels(
                    method=method, endpoint=endpoint, status="error"
                ).inc()
                return APIResponse(
                    False,
                    error=f"HTTP {e.status}: {str(e)}",
                    status_code=e.status,
                    request_id=request_id,
                )

            except Exception as e:
                circuit_breaker.record_failure()
                API_REQUESTS_TOTAL.labels(
                    method=method, endpoint=endpoint, status="error"
                ).inc()
                return APIResponse(
                    False, error=str(e), status_code=500, request_id=request_id
                )

            finally:
                ACTIVE_CONNECTIONS.dec()



    async def get_account_balance(self) -> APIResponse:
        return await self._make_request("GET", "/api/v1/account-balance/")

    async def send_mobile_money(
        self, amount: float, currency: str, recipient_number: str, reference: str
    ) -> APIResponse:
        payload = {
            "amount": amount,
            "currency": currency,
            "recipient_number": recipient_number,
            "reference": reference,
        }
        return await self._make_request(
            "POST", "/api/v1/mobile-money/send-payment/", payload
        )

    async def send_b2b_payment(
        self,
        external_reference: str,
        amount: float,
        account_number: str,
        channel: PaymentChannel,
        reason: str,
        results_url: str,
    ) -> APIResponse:
        payload = {
            "ExternalReference": external_reference,
            "Amount": amount,
            "AccountNumber": account_number,
            "Channel": channel.value,
            "Reason": reason,
            "ResultsUrl": results_url,
        }
        return await self._make_request(
            "POST", "/api/v1/mobile-money/send-payment/", payload
        )

    async def send_b2c_payment(
        self,
        external_reference: str,
        amount: float,
        phone_number: str,
        reason: str,
        results_url: str,
    ) -> APIResponse:
        payload = {
            "ExternalReference": external_reference,
            "Amount": amount,
            "PhoneNumber": phone_number,
            "Channel": "MPESA",
            "Reason": reason,
            "ResultsUrl": results_url,
        }
        return await self._make_request(
            "POST", "/api/v1/mobile-money/send-payment/", payload
        )

    async def receive_c2b_payment(
        self,
        external_reference: str,
        amount: float,
        phone_number: str,
        reason: str,
        results_url: str,
    ) -> APIResponse:
        payload = {
            "ExternalReference": external_reference,
            "Amount": amount,
            "PhoneNumber": phone_number,
            "Channel": "MPESA",
            "Reason": reason,
            "ResultsUrl": results_url,
        }
        return await self._make_request(
            "POST", "/api/v1/mobile-money/receive-payment/", payload
        )

    async def authorize_transaction(
        self, transaction_id: str, otp: str
    ) -> APIResponse:
        payload = {"TransactionID": transaction_id, "OTP": otp}
        return await self._make_request(
            "POST", "/api/v1/mobile-money/authorize-transaction/", payload
        )

    async def send_bank_payment(
        self,
        external_reference: str,
        amount: float,
        account_number: str,
        channel: PaymentChannel,
        bank_code: str,
        currency: str,
        reason: str,
        results_url: str,
    ) -> APIResponse:
        payload = {
            "ExternalReference": external_reference,
            "Amount": amount,
            "AccountNumber": account_number,
            "Channel": channel.value,
            "BankCode": bank_code,
            "Currency": currency,
            "Reason": reason,
            "ResultsUrl": results_url,
        }
        return await self._make_request(
            "POST", "/api/v1/bank/send-payment/", payload
        )

    async def query_bank_transaction(
        self, transaction_reference: str
    ) -> APIResponse:
        payload = {"TransactionReference": transaction_reference}
        return await self._make_request(
            "POST", "/api/v1/bank/transaction-query/", payload
        )

    async def query_mobile_money_transaction(
        self, transaction_reference: str
    ) -> APIResponse:
        payload = {"TransactionReference": transaction_reference}
        return await self._make_request(
            "POST", "/api/v1/mobile-money/transaction-query/", payload
        )

    async def pull_mobile_money_transactions(
        self,
        start_date: datetime,
        end_date: datetime,
        trans_type: TransactionType,
        offset_value: int = 0,
    ) -> APIResponse:
        payload = {
            "StartDate": start_date.strftime("%Y-%m-%d %H:%M:%S"),
            "EndDate": end_date.strftime("%Y-%m-%d %H:%M:%S"),
            "TransType": trans_type.value,
            "OffsetValue": offset_value,
        }
        return await self._make_request(
            "POST", "/api/v1/mobile-money/pull-transactions/", payload
        )

    async def send_airtime(
        self,
        external_reference: str,
        amount: float,
        phone_number: str,
        reason: str,
        results_url: str,
    ) -> APIResponse:
        payload = {
            "ExternalReference": external_reference,
            "Amount": amount,
            "PhoneNumber": phone_number,
            "Reason": reason,
            "ResultsUrl": results_url,
        }
        return await self._make_request(
            "POST", "/api/v1/airtime/send-airtime/", payload
        )

    async def batch_send_mobile_money(
        self, payments: List[Dict]
    ) -> List[APIResponse]:
        tasks = []
        for payment in payments:
            task = self.send_mobile_money(
                amount=payment["amount"],
                currency=payment["currency"],
                recipient_number=payment["recipient_number"],
                reference=payment["reference"],
            )
            tasks.append(task)
        return await asyncio.gather(*tasks, return_exceptions=True)


class PesaWayClientPool:
    """Pool of PesaWay clients for high concurrency"""

    def __init__(self, pool_size: int = 5, **client_kwargs):
        self.pool_size = pool_size
        self.client_kwargs = client_kwargs
        self.clients = []
        self.current_client = 0

    async def __aenter__(self):
        self.clients = []
        for _ in range(self.pool_size):
            client = PesaWayAPIClient(**self.client_kwargs)
            await client.__aenter__()
            self.clients.append(client)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        for client in self.clients:
            await client.__aexit__(exc_type, exc_val, exc_tb)

    def get_client(self) -> "PesaWayAPIClient":
        """Get next client in round-robin fashion"""
        client = self.clients[self.current_client]
        self.current_client = (self.current_client + 1) % len(self.clients)
        return client
