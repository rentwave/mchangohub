import json
import requests

class PesaWayAPIClient:
    def __init__(self, client_id, client_secret, base_url='https://api.sandbox.pesaway.com'):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url
        self.access_token = self._authenticate()

    def _authenticate(self):
        url = f"{self.base_url}/api/v1/token/"
        payload = {
            'consumer_key': self.client_id,
            'consumer_secret': self.client_secret,
            "grant_type": "client_credentials"
        }
        headers = {'Content-Type': 'application/json'}
        r = requests.post(url, headers=headers, data=json.dumps(payload))
        r.raise_for_status()
        return r.json()['data']['token']

    def _headers(self):
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }

    def _post(self, endpoint, payload=None):
        url = f"{self.base_url}{endpoint}"
        r = requests.post(url, headers=self._headers(), data=json.dumps(payload or {}))
        r.raise_for_status()
        return r.json()

    def _get(self, endpoint):
        url = f"{self.base_url}{endpoint}"
        r = requests.get(url, headers=self._headers())
        r.raise_for_status()
        return r.json()

    def get_account_balance(self):
        return self._get('/api/v1/account-balance/')

    def send_mobile_money(self, amount, currency, recipient_number, reference):
        payload = {
            "amount": amount,
            "currency": currency,
            "recipient_number": recipient_number,
            "reference": reference
        }
        return self._post('/api/v1/mobile-money/send-payment/', payload)

    def send_b2b_payment(self, external_reference, amount, account_number, channel, reason, results_url):
        payload = {
            "ExternalReference": external_reference,
            "Amount": amount,
            "AccountNumber": account_number,
            "Channel": channel,
            "Reason": reason,
            "ResultsUrl": results_url
        }
        return self._post('/api/v1/mobile-money/send-payment/', payload)

    def send_b2c_payment(self, external_reference, amount, phone_number, channel, reason, results_url):
        payload = {
            "ExternalReference": external_reference,
            "Amount": amount,
            "PhoneNumber": phone_number,
            "Channel": channel,
            "Reason": reason,
            "ResultsUrl": results_url
        }
        return self._post('/api/v1/mobile-money/send-payment/', payload)

    def receive_c2b_payment(self, external_reference, amount, phone_number, channel, reason, results_url):
        payload = {
            "ExternalReference": external_reference,
            "Amount": amount,
            "PhoneNumber": phone_number,
            "Channel": channel,
            "Reason": reason,
            "ResultsUrl": results_url
        }
        return self._post('/api/v1/mobile-money/receive-payment/', payload)

    def authorize_transaction(self, transaction_id, otp):
        payload = {
            "TransactionID": transaction_id,
            "OTP": otp
        }
        return self._post('/api/v1/mobile-money/authorize-transaction/', payload)

    def send_bank_payment(self, external_reference, amount, account_number, channel, bank_code, currency, reason, results_url):
        payload = {
            "ExternalReference": external_reference,
            "Amount": amount,
            "AccountNumber": account_number,
            "Channel": channel,
            "BankCode": bank_code,
            "Currency": currency,
            "Reason": reason,
            "ResultsUrl": results_url
        }
        return self._post('/api/v1/bank/send-payment/', payload)

    def query_bank_transaction(self, transaction_reference):
        payload = {
            "TransactionReference": transaction_reference
        }
        return self._post('/api/v1/bank/transaction-query/', payload)

    def query_mobile_money_transaction(self, transaction_reference):
        payload = {
            "TransactionReference": transaction_reference
        }
        return self._post('/api/v1/mobile-money/transaction-query/', payload)

    def pull_mobile_money_transactions(self, start_date, end_date, trans_type, offset_value=0):
        payload = {
            "StartDate": start_date.strftime("%Y-%m-%d %H:%M:%S"),
            "EndDate": end_date.strftime("%Y-%m-%d %H:%M:%S"),
            "TransType": trans_type,
            "OffsetValue": offset_value
        }
        return self._post('/api/v1/mobile-money/pull-transactions/', payload)

    def send_airtime(self, external_reference, amount, phone_number, reason, results_url):
        payload = {
            "ExternalReference": external_reference,
            "Amount": amount,
            "PhoneNumber": phone_number,
            "Reason": reason,
            "ResultsUrl": results_url
        }
        return self._post('/api/v1/airtime/send-airtime/', payload)
