from django.urls import path

from otps.views import OTPAPIHandler

handler = OTPAPIHandler()

urlpatterns = [
    path('send/', handler.send_otp, name='otp-send'),
    path('verify/', handler.verify_otp, name='otp-verify'),
]
