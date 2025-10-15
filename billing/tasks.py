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
from billing.views import TransactionStatus

logger = logging.getLogger(__name__)


@shared_task
def check_transaction_status():
    """
    Periodically checks 'Pending' topup & payment transactions and reconciles them with PesaWay.
    - Approves successful ones.
    - Rejects failed ones.
    - Skips already processed.
    """
    try:
        client = PesaWayAPIClient(
            client_id=settings.PESAWAY_CLIENT_ID,
            client_secret=settings.PESAWAY_CLIENT_SECRET,
            base_url=getattr(settings, "PESAWAY_BASE_URL", "https://api.pesaway.com"),
            timeout=getattr(settings, "PESAWAY_TIMEOUT", 30),
        )

        service = WalletTransactionService()
        processed_count = 0

        # Define transaction processors
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

        # Check transactions pending for 5–15 minutes
        time_upper = timezone.now() - timedelta(minutes=3)
        time_lower = timezone.now() - timedelta(days=15)
        logger.info(f"Checking pending transactions created between {time_lower} and {time_upper}")

        # Iterate through topups and payments
        for trx_type in ["topup", "payment"]:
            pending_transactions = service.filter(
                status__name="Pending",
                transaction_type=trx_type,
                date_created__gte=time_lower,
                date_created__lte=time_upper,
            )

            if not pending_transactions:
                logger.info(f"No pending {trx_type} transactions found in the time window.")
                continue

            for trx in pending_transactions:
                try:
                    response = client.query_mobile_money_transaction(
                        transaction_reference=trx.receipt_number
                    )

                    data = getattr(response, "data", None) or response.data
                    result_code = data.get("ResultCode")
                    result_desc = str(data.get("ResultDesc", "")).lower()
                    reference = data.get("OriginatorReference")
                    receipt = data.get("TransactionID")

                    if not reference or not receipt:
                        logger.warning(f"{trx_type} {trx.id} missing reference/receipt → {data}")
                        continue

                    # Skip already processed ones
                    if trx.status.name.lower() != "pending":
                        logger.info(f"Skipping {trx_type} {trx.id} — already processed")
                        continue

                    # Determine outcome
                    if result_code == TransactionStatus.SUCCESS and "success" in result_desc:
                        processor = processors["approve"][trx_type]
                        action = "approved"
                    elif result_code == TransactionStatus.FAILED or "fail" in result_desc:
                        processor = processors["reject"][trx_type]
                        action = "rejected"
                    else:
                        logger.info(f"{trx_type} {trx.id} still pending → {result_desc}")
                        continue  # still pending, skip

                    # Execute action
                    result = processor.post(request=None, reference=reference, receipt=receipt)
                    processed_count += 1

                    logger.info(f"{trx_type.capitalize()} {action}: {trx.id} → {result}")

                except Exception as err:
                    logger.error(
                        f"Error processing {trx_type} transaction {trx.id}: {err}",
                        exc_info=True,
                    )
        logger.info(f"Transaction status check complete → {processed_count} processed successfully")
        return {"success": True, "processed": processed_count}
    except Exception as e:
        logger.exception("Unexpected error in transaction status checker")
        return {"success": False, "message": str(e)}
