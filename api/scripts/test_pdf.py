import requests

resp = requests.post(url="https://zentu.rentwaveafrica.co.ke/api/statements/summary/", data={
    "contribution":"9ea59c9f-9db7-4ad6-aad8-3e71149a2f90"
})
print(resp)