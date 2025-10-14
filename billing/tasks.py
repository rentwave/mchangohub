import logging
from datetime import timedelta
from celery import shared_task
from django.utils import timezone
from django.conf import settings
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

logger = logging.getLogger(__name__)


@shared_task
def check_transaction_status():
    """
    Periodically checks and processes pending transactions (topup & payment).
    Approves successful ones, rejects failed ones.
    """
    try:
        client = PesaWayAPIClient(
            client_id=settings.PESAWAY_CLIENT_ID,
            client_secret=settings.PESAWAY_CLIENT_SECRET,
            base_url=getattr(settings, "PESAWAY_BASE_URL", "https://api.pesaway.com"),
            timeout=getattr(settings, "PESAWAY_TIMEOUT", 30),
        )

        service = WalletTransactionService()

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
        time_gte = timezone.now() - timedelta(minutes=10)
        time_lte = timezone.now() - timedelta(minutes=5)
        logger.info(f"Checking pending transactions created between {time_gte} and {time_lte}")
        for trx_type in ["topup", "payment"]:
            pending = service.filter(
                status__name="Pending",
                transaction_type=trx_type,
                date_created__gte=time_gte,
                date_created__lte=time_lte,
            )
            for trx in pending:
                try:
                    response = client.query_mobile_money_transaction(
                        transaction_reference=trx.receipt_number
                    )
                    data = getattr(response, "data", None) or response.json()
                    result_code = data.get("ResultCode")
                    result_desc = data.get("ResultDesc", "").lower()
                    reference = data.get("OriginatorReference")
                    receipt = data.get("TransactionID")

                    if not reference or not receipt:
                        logger.warning(f"{trx_type} {trx.id} missing reference/receipt → {data}")
                        continue
                    if result_code == 0:
                        processor = processors["approve"][trx_type]
                        action = "approved"
                    else:
                        processor = processors["reject"][trx_type]
                        action = "rejected"
                    result = processor.post(request=None, reference=reference, receipt=receipt)
                    processed_count += 1
                    logger.info(f"{trx_type.capitalize()} {action}: {trx.id} → {result}")
                except Exception as err:
                    logger.error(f"Failed to process {trx_type} transaction {trx.id}: {err}", exc_info=True)
        logger.info(f"Transaction status check completed → {processed_count} processed")
        return {"success": True, "processed": processed_count}
    except Exception as e:
        logger.exception("Unexpected error while checking transactions")
        return {"success": False, "message": str(e)}

