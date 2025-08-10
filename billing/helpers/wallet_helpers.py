from datetime import datetime, timedelta
from django.db.models import Sum
from billing.models import WalletAccount, WalletTransaction


def get_wallet_summary():
    wallets = WalletAccount.objects.all()
    total_balance = sum(wallet.balance for wallet in wallets)
    active_wallets = wallets.filter(is_active=True).count()
    return {
        "total_balance": total_balance,
        "wallet_count": wallets.count(),
        "active_wallets": active_wallets
    }

def get_recent_transactions(limit=10):
    return WalletTransaction.objects.select_related("wallet").order_by("-timestamp")[:limit]

def get_top_contributors(limit=5):
    return (
        WalletTransaction.objects.filter(type="CREDIT")
        .values("wallet__owner__name")
        .annotate(total_amount=Sum("amount"))
        .order_by("-total_amount")[:limit]
    )

def get_daily_trend(days=7):
    today = datetime.today()
    trend = []
    for i in range(days):
        day = today - timedelta(days=i)
        amount = WalletTransaction.objects.filter(timestamp__date=day.date()).aggregate(total=Sum("amount"))["total"] or 0
        trend.append({"date": day.strftime("%Y-%m-%d"), "total": amount})
    return list(reversed(trend))
