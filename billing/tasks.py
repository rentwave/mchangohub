import logging
from datetime import timedelta
from celery import shared_task
from django.utils import timezone
from base.backend.service import WalletTransactionService
from billing.backend.interfaces.payment import (
    ApprovePaymentTransaction,
    RejectPaymentTransaction,
)
from billing.backend.interfaces.topup import (
    ApproveTopupTransaction,
    RejectTopupTransaction,
)
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
    Periodically checks and processes pending transactions (topup & payment).
    Returns a summary of how many were processed successfully.
    """
    try:
        client = PesaWayAPIClient(
            client_id=settings.PESAWAY_CLIENT_ID,
            client_secret=settings.PESAWAY_CLIENT_SECRET,
            base_url=getattr(settings, "PESAWAY_BASE_URL", "https://api.pesaway.com"),
            timeout=getattr(settings, "PESAWAY_TIMEOUT", 30),
        )

        processors = {
            "approve": {
                "topup": ApproveTopupTransaction(),
                "payment": ApprovePaymentTransaction(),
            },
            "reject": {
                "topup": RejectTopupTransaction(),
                "payment": RejectPaymentTransaction(),
            },
        }

        processed_count = 0
        time_threshold = timezone.now() - timedelta(minutes=1)
        logger.info(f"Checking pending transactions before {time_threshold}")

        service = WalletTransactionService()
        def process_transactions(action_type: str):
            nonlocal processed_count
            for trx_type, processor in processors[action_type].items():
                pending = service.filter(
                    status__name="Pending",
                    transaction_type=trx_type,
                    date_created__lte=time_threshold,
                )
                for trx in pending:
                    try:
                        response = client.query_mobile_money_transaction(
                            transaction_reference=trx.receipt_number
                        )
                        data = response.data or {}
                        result_code = data.get("ResultCode")
                        result_desc = data.get("ResultDesc", "").lower()
                        reference = data.get("OriginatorReference")
                        receipt = data.get("TransactionID")
                        if not reference or not receipt:
                            logger.warning(
                                f"{trx_type.capitalize()} {trx.id} missing reference/receipt → {data}"
                            )
                            continue
                        # Skip if already processed
                        if (
                            (action_type == "approve" and result_code == 2001 and "failed" in result_desc)
                            or (action_type == "reject" and result_code == 0 and "successful" in result_desc)
                        ):
                            logger.info(
                                f"Skipping {trx_type} {trx.id} — already processed: {result_desc}"
                            )
                            continue

                        result = processor.post(request=None, reference=reference, receipt=receipt)
                        processed_count += 1
                        logger.info(
                            f"{trx_type.capitalize()} {action_type}d: {trx.id} → {result}"
                        )

                    except Exception as err:
                        logger.error(
                            f"Failed to {action_type} {trx_type} transaction {trx.id}: {err}",
                            exc_info=True,
                        )
        process_transactions("approve")
        process_transactions("reject")
        return {"success": True, "processed": processed_count}

    except Exception as e:
        logger.exception("Unexpected error while checking transactions")
        return {"success": False, "message": str(e)}
