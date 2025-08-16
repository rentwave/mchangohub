# import json
# import requests
# from datetime import datetime, timedelta
#
# class PesaWayAPI:
#     def __init__(self, client_id, client_secret, base_url='https://api.sandbox.pesaway.com'):
#         self.client_id = client_id
#         self.client_secret = client_secret
#         self.base_url = base_url
#         self.access_token = self.authenticate()
#
#     def authenticate(self):
#         url = f"{self.base_url}/api/v1/token/"
#         headers = {'Content-Type': 'application/json'}
#         payload = {
#             'consumer_key': self.client_id,
#             'consumer_secret': self.client_secret,
#             "grant_type": "client_credentials"
#         }
#         response = requests.post(url, headers=headers, data=json.dumps(payload))
#         if response.status_code == 200:
#             return response.json().get('data', {}).get('token')
#         else:
#             raise Exception(f"Authentication failed: {response.text}")
#
#     def get_headers(self):
#         return {
#             'Authorization': f'Bearer {self.access_token}',
#             'Content-Type': 'application/json'
#         }
#
#     def request(self, endpoint, method='POST', payload=None):
#         url = f"{self.base_url}{endpoint}"
#         headers = self.get_headers()
#         if method.upper() == 'POST':
#             response = requests.post(url, headers=headers, data=json.dumps(payload or {}))
#         elif method.upper() == 'GET':
#             response = requests.get(url, headers=headers)
#         else:
#             raise ValueError("Unsupported HTTP method")
#         return response.json()
#
# if __name__ == "__main__":
#     client_id = "4yN4wTqhNDRRKY6oMksGVbTa9Q8xP0px"
#     client_secret = "S9zRS9Q3f7DBkC7I"
#     pesaway = PesaWayAPI(client_id=client_id, client_secret=client_secret)
#
#     try:
#         balance = pesaway.request('/api/v1/account-balance/', method='GET')
#         print("✅ Account Balance:", balance)
#     except Exception as e:
#         print("❌ Balance Check Failed:", e)
#
#     # try:
#     #     mobile_payload = {
#     #         "amount": 1,
#     #         "currency": "KES",
#     #         "recipient_number": "254710956633",
#     #         "reference": "MMT123"
#     #     }
#     #     response = pesaway.request('/api/v1/mobile-money/send-payment/', payload=mobile_payload)
#     #     print("✅ Mobile Money Transfer Response:", response)
#     # except Exception as e:
#     #     print("❌ Mobile Money Transfer Failed:", e)
#     #
#     # try:
#     #     b2b_payload = {
#     #         "ExternalReference": "1234",
#     #         "Amount": 30,
#     #         "AccountNumber": "12345",
#     #         "Channel": "MPESA Paybill",
#     #         "Reason": "Payment of transportation fee",
#     #         "ResultsUrl": "https://yourdomain.com/result_url"
#     #     }
#     #     response = pesaway.request('/api/v1/mobile-money/send-payment/', payload=b2b_payload)
#     #     print("✅ B2B Transfer Response:", response)
#     # except Exception as e:
#     #     print("❌ B2B Transfer Failed:", e)
#     #
#     # try:
#     #     b2c_payload = {
#     #         "ExternalReference": "VAHBDHJSJHBAJFHBDSJHJBSHJDBH",
#     #         "Amount": 30,
#     #         "PhoneNumber": "254710000008",
#     #         "Channel": "MPESA",
#     #         "Reason": "Payment of transportation fee",
#     #         "ResultsUrl": "https://yourdomain.com/result_url"
#     #     }
#     #     response = pesaway.request('/api/v1/mobile-money/send-payment/', payload=b2c_payload)
#     #     print("✅ B2C Transfer Response:", response)
#     # except Exception as e:
#     #     print("❌ B2C Transfer Failed:", e)
#
#     # try:
#     #     c2b_payload = {
#     #         "ExternalReference": "65748394",
#     #         "Amount": 30,
#     #         "PhoneNumber": "254710956633",
#     #         "Channel": "MPESA",
#     #         "Reason": "Payment of transportation fee",
#     #         "ResultsUrl": "https://yourdomain.com/result_url"
#     #     }
#     #     response = pesaway.request('/api/v1/mobile-money/receive-payment/', payload=c2b_payload)
#     #     print("✅ C2B Payment Response:", response)
#     # except Exception as e:
#     #     print("❌ C2B Transfer Failed:", e)
#
#     # try:
#     #     auth_payload = {
#     #         "TransactionID": "PHYD5AD5ASDF5",
#     #         "OTP": "12345"
#     #     }
#     #     response = pesaway.request('/api/v1/mobile-money/authorize-transaction/', payload=auth_payload)
#     #     print("✅ Authorization Response:", response)
#     # except Exception as e:
#     #     print("❌ Authorization Failed:", e)
#
#     # try:
#     #     bank_payload = {
#     #         "ExternalReference": "202412231446",
#     #         "Amount": 30,
#     #         "AccountNumber": "01**********4",
#     #         "Channel": "Bank",
#     #         "BankCode": "01",
#     #         "Currency": "KES",
#     #         "Reason": "Salary payment",
#     #         "ResultsUrl": "https://yourdomain.com/api/webhook"
#     #     }
#     #     response = pesaway.request('/api/v1/bank/send-payment/', payload=bank_payload)
#     #     print("✅ Bank Payment Response:", response)
#     # except Exception as e:
#     #     print("❌ Bank Payment Failed:", e)
#     #
#     # try:
#     #     query_bank_payload = {
#     #         "TransactionReference": "PHYE75C6CACD2"
#     #     }
#     #     response = pesaway.request('/api/v1/bank/transaction-query/', payload=query_bank_payload)
#     #     print("✅ Bank Transaction Query Response:", response)
#     # except Exception as e:
#     #     print("❌ Bank Transaction Query Failed:", e)
#     #
#     try:
#         query_mobile_payload = {
#             "TransactionReference": "PHYE75C6CACD2"
#         }
#         response = pesaway.request('/api/v1/mobile-money/transaction-query/', payload=query_mobile_payload)
#         print("✅ Mobile Money Transaction Query Response:", response)
#     except Exception as e:
#         print("❌ Mobile Money Transaction Query Failed:", e)
#
#     # try:
#     #     now = datetime.utcnow()
#     #     start_time = now - timedelta(hours=1)
#     #     end_time = now
#     #     pull_payload = {
#     #         "StartDate": start_time.strftime("%Y-%m-%d %H:%M:%S"),
#     #         "EndDate": end_time.strftime("%Y-%m-%d %H:%M:%S"),
#     #         "TransType": "Collection",
#     #         "OffsetValue": 0
#     #     }
#     #     response = pesaway.request('/api/v1/mobile-money/pull-transactions/', payload=pull_payload)
#     #     print("✅ Pulled Transactions:", response)
#     # except Exception as e:
#     #     print("❌ Pull Transactions Failed:", e)
#     #
#     # try:
#     #     airtime_payload = {
#     #         "ExternalReference": "AIR123",
#     #         "Amount": 30,
#     #         "PhoneNumber": "254710000001",
#     #         "Reason": "Airtime of project ABC of transportation fee",
#     #         "ResultsUrl": "https://yourdomain.com/result_url"
#     #     }
#     #     response = pesaway.request('/api/v1/airtime/send-airtime/', payload=airtime_payload)
#     #     print("✅ Airtime Response:", response)
#     # except Exception as e:
#     #     print("❌ Airtime Response Failed:", e)
