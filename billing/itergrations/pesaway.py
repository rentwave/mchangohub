import requests
import json
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass
from enum import Enum


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


class PesaWayAPIClient:
    def __init__(
            self,
            client_id: str,
            client_secret: str,
            base_url: str,
            timeout: int = 30
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.token = None

    def _authenticate(self) -> str:
        """Get authentication token"""
        url = f"{self.base_url}/api/v1/token/"
        payload = {
            "consumer_key": self.client_id,
            "consumer_secret": self.client_secret,
            "grant_type": "client_credentials",
        }
        response = requests.post(url, json=payload, timeout=self.timeout)
        print("Auth response status:", response.status_code)
        print("Auth response text:", response.text)
        response.raise_for_status()
        data = response.json()
        token = data["data"]["token"]
        self.token = token

        return token

    def _get_headers(self) -> Dict[str, str]:
        """Get headers with valid token"""
        # Always get fresh token (no caching)
        self._authenticate()

        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _make_request(
            self,
            method: str,
            endpoint: str,
            payload: Optional[Dict] = None,
    ) -> APIResponse:
        """Make HTTP request to API"""
        try:
            headers = self._get_headers()
            url = f"{self.base_url}{endpoint}"
            print("Making request to:", url)
            print("With payload:", payload)
            print("Method:", method)
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, timeout=self.timeout)
            else:
                response = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
            print("Response status:", response.status_code)
            print("Response text:", response.text)
            if response.status_code == 401:
                self._authenticate()
                headers = self._get_headers()
                if method.upper() == "GET":
                    response = requests.get(url, headers=headers, timeout=self.timeout)
                else:
                    response = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
                print("Response status:", response.status_code)
                print("Response text:", response.text)
            print(response.status_code, response.text)
            response.raise_for_status()
            data = response.json()
            return APIResponse(
                success=True,
                data=data,
                status_code=response.status_code
            )

        except requests.exceptions.HTTPError as e:
            return APIResponse(
                success=False,
                error=f"HTTP {e.response.status_code}: {str(e)}",
                status_code=e.response.status_code if e.response else None
            )
        except Exception as e:
            return APIResponse(
                success=False,
                error=str(e),
                status_code=500
            )

    def get_account_balance(self) -> APIResponse:
        return self._make_request("GET", "/api/v1/account-balance/")

    def send_mobile_money(
            self, amount: float, currency: str, recipient_number: str, reference: str
    ) -> APIResponse:
        payload = {
            "amount": amount,
            "currency": currency,
            "recipient_number": recipient_number,
            "reference": reference,
        }
        return self._make_request("POST", "/api/v1/mobile-money/send-payment/", payload)

    def send_b2b_payment(
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
        return self._make_request("POST", "/api/v1/mobile-money/send-payment/", payload)

    def send_b2c_payment(
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
        return self._make_request("POST", "/api/v1/mobile-money/send-payment/", payload)

    def receive_c2b_payment(
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
        print("Receiving C2B Payment with payload:", payload)
        return self._make_request("POST", "/api/v1/mobile-money/receive-payment/", payload)

    def authorize_transaction(self, transaction_id: str, otp: str) -> APIResponse:
        payload = {"TransactionID": transaction_id, "OTP": otp}
        return self._make_request("POST", "/api/v1/mobile-money/authorize-transaction/", payload)

    def send_bank_payment(
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
        return self._make_request("POST", "/api/v1/bank/send-payment/", payload)

    def query_bank_transaction(self, transaction_reference: str) -> APIResponse:
        payload = {"TransactionReference": transaction_reference}
        return self._make_request("POST", "/api/v1/bank/transaction-query/", payload)

    def query_mobile_money_transaction(self, transaction_reference: str) -> APIResponse:
        payload = {"TransactionReference": transaction_reference}
        return self._make_request("POST", "/api/v1/mobile-money/transaction-query/", payload)

    def pull_mobile_money_transactions(
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
        return self._make_request("POST", "/api/v1/mobile-money/pull-transactions/", payload)

    def send_airtime(
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
        return self._make_request("POST", "/api/v1/airtime/send-airtime/", payload)

