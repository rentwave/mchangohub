from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from base.backend.service import WalletTransactionService
from billing.backend.interfaces.payment import RejectPaymentTransaction, ApprovePaymentTransaction
from billing.backend.interfaces.topup import RejectTopupTransaction, ApproveTopupTransaction
from billing.itergrations.pesaway import PesaWayAPIClient
from billing.views import TransactionStatus
client = PesaWayAPIClient(
    client_id=settings.PESAWAY_CLIENT_ID,
    client_secret=settings.PESAWAY_CLIENT_SECRET,
    base_url=getattr(settings, "PESAWAY_BASE_URL", "https://api.pesaway.com"),
    timeout=getattr(settings, "PESAWAY_TIMEOUT", 30),
)
service = WalletTransactionService()
processed_count = 0
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
time_upper = timezone.now() - timedelta(minutes=3)
time_lower = timezone.now() - timedelta(days=15)
print(f"Checking pending transactions created between {time_lower} and {time_upper}")
for trx_type in ["topup", "payment"]:
    pending_transactions = service.filter(
        status__name="Pending",
        transaction_type=trx_type,
        date_created__gte=time_lower,
        date_created__lte=time_upper,
    )
    print(pending_transactions)
    if not pending_transactions:
        print(f"No pending {trx_type} transactions found in the time window.")
        continue
    for trx in pending_transactions:
        print(trx)
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
                print(f"{trx_type} {trx.id} missing reference/receipt → {data}")
                continue
            if trx.status.name.lower() != "pending":
                print(f"Skipping {trx_type} {trx.id} — already processed")
                continue
            if result_code == TransactionStatus.SUCCESS and "success" in result_desc:
                processor = processors["approve"][trx_type]
                action = "approved"
            elif result_code == TransactionStatus.FAILED or "fail" in result_desc:
                processor = processors["reject"][trx_type]
                action = "rejected"
            else:
                print(f"{trx_type} {trx.id} still pending → {result_desc}")
                continue  # still pending, skip
            result = processor.post(request=None, reference=reference, receipt=receipt)
            processed_count += 1
            print(f"{trx_type.capitalize()} {action}: {trx.id} → {result}")
        except Exception as err:
            print(
                f"Error processing {trx_type} transaction {trx.id}: {err}",
            )
print(f"Transaction status check complete → {processed_count} processed successfully")
