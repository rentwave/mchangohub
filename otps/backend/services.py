from otps.models import OTP
from utils.service_base import ServiceBase


class OTPService(ServiceBase):
    manager = OTP.objects