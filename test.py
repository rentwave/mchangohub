import requests

url = "https://api.pesaway.com/api/v1/token/"
headers = {
    "Content-Type": "application/json"
}
payload = {
    "consumer_key": "@8E1th1@!WXq9C;&_@L;6e03&93re#20",
    "consumer_secret": "941CUfQEP_7DpU50",
    "grant_type": "client_credentials"
}

response = requests.post(url, headers=headers, json=payload)

print("Status code:", response.status_code)
print("Response:", response.json())
