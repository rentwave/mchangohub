from datetime import datetime, timedelta
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

from celery import shared_task

from base.backend.service import WalletTransactionService
from billing.backend.processes import ApproveTopupTransaction, ApprovePaymentTransaction
from billing.itergrations.pesaway import PesaWayAPIClient
from mchangohub import settings

logger = logging.getLogger(__name__)


@dataclass
class APIResponse:
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    status_code: Optional[int] = None


@shared_task
def check_transaction_status() -> APIResponse:
    """
    Check and approve pending transactions (topup & payment) within the last 10 minutes.
    Returns an APIResponse object.
    """
    try:
        client = PesaWayAPIClient(
            client_id=settings.PESAWAY_CLIENT_ID,
            client_secret=settings.PESAWAY_CLIENT_SECRET,
            base_url=getattr(settings, 'PESAWAY_BASE_URL', 'https://api.pesaway.com'),
            timeout=getattr(settings, 'PESAWAY_TIMEOUT', 30)
        )
        transaction_processors = {
            "topup": ApproveTopupTransaction(),
            "payment": ApprovePaymentTransaction(),
        }
        processed_count = 0
        for trx_type, processor in transaction_processors.items():
            pending_transactions = WalletTransactionService().filter(
                state__name="Pending",
                transaction_type=trx_type,
                date_created__gte=datetime.now() - timedelta(minutes=10)
            )
            for trx in pending_transactions:
                try:
                    response = client.query_mobile_money_transaction(
                        transaction_reference=trx.receipt_number
                    ) or {}
                    result_code = response.get("ResultCode")
                    if result_code != 0:
                        logger.info(f"Skipping {trx_type} {trx.id}, not successful → {response}")
                        continue
                    reference = response.get("OriginatorReference")
                    receipt = response.get("TransactionID")
                    if not reference or not receipt:
                        logger.warning(
                            f"{trx_type.capitalize()} {trx.id} missing reference/receipt in response → {response}"
                        )
                        continue
                    if trx.state.name.lower() == "pending":
                        approval_result = processor.post(reference=reference, receipt=receipt)
                        logger.info(
                            f"{trx_type.capitalize()} transaction approved: {trx.id} → {approval_result}"
                        )
                        processed_count += 1
                    else:
                        logger.info(f"{trx_type.capitalize()} {trx.id} already processed, skipping.")
                except Exception as trx_err:
                    logger.error(
                        f"Failed processing {trx_type} transaction {trx.id}: {trx_err}",
                        exc_info=True
                    )
        return APIResponse(
            success=True,
            data={"processed": processed_count},
            status_code=200
        )
    except Exception as e:
        logger.exception("Unexpected error while checking transactions")
        return APIResponse(
            success=False,
            error=str(e),
            status_code=500
        )
