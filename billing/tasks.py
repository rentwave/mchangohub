import logging
from threading import Thread
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import timedelta

from celery import shared_task
from django.http import JsonResponse
from django.utils import timezone

from base.backend.service import WalletTransactionService
from billing.backend.interfaces.payment import ApprovePaymentTransaction
from billing.backend.interfaces.topup import ApproveTopupTransaction
from billing.helpers.cronjobs import Automate
from billing.itergrations.pesaway import PesaWayAPIClient
from mchangohub import settings

logger = logging.getLogger(__name__)



@shared_task
def check_transaction_status():
    """
    Check and approve pending transactions (topup & payment) within the last 10 minutes.
    Returns an APIResponse object.
    """
    try:
        ex = Thread(target=Automate().check_transactions())
        ex.daemon = True
        ex.start()
    except Exception as e:
        logger.exception("Unexpected error while checking transactions")
        return JsonResponse({"status": "error", "message": str(e)}, status=500)
