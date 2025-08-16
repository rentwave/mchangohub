import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from base.backend.service import WalletTransactionService
from billing.backend.interfaces.payment import ApprovePaymentTransaction
from billing.backend.interfaces.topup import ApproveTopupTransaction
from billing.itergrations.pesaway import PesaWayAPIClient
from mchangohub import settings

logger = logging.getLogger(__name__)


@dataclass
class APIResponse:
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    status_code: Optional[int] = None

    def get(self, key: str, default=None):
        """
        Dict-like safe getter for data.
        Example: response.get("processed", 0)
        """
        if self.data and key in self.data:
            return self.data[key]
        return default

    def to_dict(self) -> Dict[str, Any]:
        """Convert APIResponse into a dict for JSON/logging."""
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "status_code": self.status_code,
        }


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
        time_threshold = timezone.now() - timedelta(minutes=2)  #  Nairobi-aware timestamp
        for trx_type, processor in transaction_processors.items():
            pending_transactions = WalletTransactionService().filter(
                state__name="Pending",
                transaction_type=trx_type,
                date_created__gte=time_threshold
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
                        approval_result = processor.post(request=None, reference=reference, receipt=receipt)
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
