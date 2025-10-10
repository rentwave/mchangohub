import logging
from datetime import timedelta
from celery import shared_task
from django.http import JsonResponse
from django.utils import timezone
from base.backend.service import WalletTransactionService
from billing.backend.interfaces.payment import ApprovePaymentTransaction
from billing.backend.interfaces.topup import ApproveTopupTransaction
from billing.itergrations.pesaway import PesaWayAPIClient
from mchangohub import settings

logger = logging.getLogger(__name__)


class ErrorCodes:
    SUCCESS = "200.001"
    TRANSACTION_FAILED = "403.033"
    VALIDATION_ERROR = "400.001"
    RATE_LIMIT_EXCEEDED = "429.001"
    INTERNAL_ERROR = "999.999.999"

@shared_task
def check_transaction_status():
    """
    Check and approve pending transactions (topup & payment) within the last 1 minute.
    Returns a dictionary indicating success and number processed.
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
        time_threshold = timezone.now() - timedelta(minutes=1)
        logger.info(f"Checking pending transactions since {time_threshold} (Nairobi time)")

        service = WalletTransactionService()

        for trx_type, processor in transaction_processors.items():
            pending_transactions = service.filter(
                status__name="Pending",
                transaction_type=trx_type,
                date_created__lte=time_threshold
            )

            for trx in pending_transactions:
                try:
                    response = client.query_mobile_money_transaction(
                        transaction_reference=trx.receipt_number
                    )

                    result_code = response.data.get("ResultCode")
                    result_desc = response.data.get("ResultDesc", "").lower()

                    if result_code == 0 and "successfully" in result_desc:
                        logger.info(f"Skipping {trx_type} {trx.id} — already successful: {result_desc}")
                        continue

                    reference = response.data.get("OriginatorReference")
                    receipt = response.data.get("TransactionID")

                    if not reference or not receipt:
                        logger.warning(
                            f"{trx_type.capitalize()} {trx.id} missing reference or receipt in response → {response}"
                        )
                        continue
                    approval_result = processor.post(
                        request=None, reference=reference, receipt=receipt
                    )
                    logger.info(
                        f"{trx_type.capitalize()} transaction approved: {trx.id} → {approval_result}"
                    )
                    processed_count += 1
                except Exception as trx_err:
                    logger.error(
                        f"Failed processing {trx_type} transaction {trx.id}: {trx_err}",
                        exc_info=True
                    )
        return {"success": True, "processed": processed_count}
    except Exception as e:
        logger.exception("Unexpected error while checking transactions")
        return {"success": False, "message": str(e)}
