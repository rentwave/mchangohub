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


def _get_pesaway_client():
    """Create a reusable Pesaway API client."""
    return PesaWayAPIClient(
        client_id=settings.PESAWAY_CLIENT_ID,
        client_secret=settings.PESAWAY_CLIENT_SECRET,
        base_url=getattr(settings, "PESAWAY_BASE_URL", "https://api.pesaway.com"),
        timeout=getattr(settings, "PESAWAY_TIMEOUT", 30),
    )


def _get_time_window():
    """Returns the lower and upper time bounds for reconciliation."""
    time_upper = timezone.now() - timedelta(minutes=3)
    time_lower = timezone.now() - timedelta(days=15)
    return time_lower, time_upper


def _process_pending_transactions(transactions, trx_type, client, approve_handler, reject_handler):
    """Shared logic for processing a list of pending transactions."""
    processed_count = 0

    for trx in transactions:
        try:
            response = client.query_mobile_money_transaction(transaction_reference=trx.receipt_number)
            data = getattr(response, "data", None) or response.data

            result_code = data.get("ResultCode")
            result_desc = str(data.get("ResultDesc", "")).lower()
            reference = data.get("OriginatorReference")
            receipt = data.get("TransactionID")

            if not reference or not receipt:
                logger.warning(f"{trx_type} {trx.id} missing reference/receipt → {data}")
                continue

            if trx.status.name.lower() != "pending":
                logger.info(f"Skipping {trx_type} {trx.id} — already processed")
                continue

            if result_code == TransactionStatus.SUCCESS:
                result = approve_handler.post(request=None, reference=reference, receipt=receipt)
                logger.info(f"{trx_type.capitalize()} approved: {trx.id} → {result}")
            else:
                result = reject_handler.post(request=None, reference=reference, receipt=receipt)
                logger.info(f"{trx_type.capitalize()} rejected: {trx.id} → {result}")


            processed_count += 1

        except Exception as err:
            logger.error(f"Error processing {trx_type} transaction {trx.id}: {err}", exc_info=True)

    return processed_count


def fetch_pending_topups():
    """Fetch all pending topup transactions within the time window."""
    service = WalletTransactionService()
    time_lower, time_upper = _get_time_window()

    return service.filter(
        status__name="Pending",
        transaction_type="topup",
        date_created__gte=time_lower,
        date_created__lte=time_upper,
    )


def fetch_pending_payments():
    """Fetch all pending payment transactions within the time window."""
    service = WalletTransactionService()
    time_lower, time_upper = _get_time_window()

    return service.filter(
        status__name="Pending",
        transaction_type="payment",
        date_created__gte=time_lower,
        date_created__lte=time_upper,
    )


@shared_task
def check_topup_status():
    """Celery task to check and process pending topup transactions."""
    try:
        client = _get_pesaway_client()
        transactions = fetch_pending_topups()

        if not transactions:
            logger.info("No pending topup transactions found.")
            return {"success": True, "processed": 0}

        count = _process_pending_transactions(
            transactions,
            "topup",
            client,
            ApproveTopupTransaction(),
            RejectTopupTransaction(),
        )

        logger.info(f"Topup reconciliation complete → {count} processed.")
        return {"success": True, "processed": count}

    except Exception as e:
        logger.exception("Error in topup status check")
        return {"success": False, "message": str(e)}


@shared_task
def check_payment_status():
    """Celery task to check and process pending payment transactions."""
    try:
        client = _get_pesaway_client()
        transactions = fetch_pending_payments()

        if not transactions:
            logger.info("No pending payment transactions found.")
            return {"success": True, "processed": 0}

        count = _process_pending_transactions(
            transactions,
            "payment",
            client,
            ApprovePaymentTransaction(),
            RejectPaymentTransaction(),
        )

        logger.info(f"Payment reconciliation complete → {count} processed.")
        return {"success": True, "processed": count}

    except Exception as e:
        logger.exception("Error in payment status check")
        return {"success": False, "message": str(e)}
