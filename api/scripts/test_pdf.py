# import requests
#
# resp = requests.post(
#     url="https://mchangohub.com/api/statements/summary/",
#     json={"contribution": "9ea59c9f-9db7-4ad6-aad8-3e71149a2f90"},
# )
#
# if resp.status_code == 200 and resp.headers.get("content-type") == "application/pdf":
#     with open("summary.pdf", "wb") as f:
#         f.write(resp.content)
#     print("✅ PDF saved as statement.pdf")
# else:
#     print(f"❌ Failed: {resp.status_code}")
#     print(resp.text[:500])
