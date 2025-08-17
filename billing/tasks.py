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
        time_threshold = timezone.now() - timedelta(hours=24)  # Nairobi-aware timestamp
        print(
            f"Checking transactions since {time_threshold} (Nairobi time)"
        )
        for trx_type, processor in transaction_processors.items():
            print(trx_type, processor)
            pending_transactions = WalletTransactionService().filter(
                status__name="Pending",
                transaction_type=trx_type,
                date_created__gte=time_threshold
            )
            for trx in pending_transactions:
                print(trx)
                try:
                    response = client.query_mobile_money_transaction(
                        transaction_reference=trx.receipt_number
                    )
                    if not response.success or response.data.get('code') != ErrorCodes.SUCCESS:
                        logger.info(f"Skipping {trx_type} {trx.id}, not successful → {response}")
                        continue
                    reference = response.data.get("OriginatorReference")
                    receipt = response.data.get("TransactionID")
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
        return {"success": True, "processed": processed_count}
    except Exception as e:
        logger.exception("Unexpected error while checking transactions")
        return JsonResponse({"status": "error", "message": str(e)}, status=500)
