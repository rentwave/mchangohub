from decimal import Decimal
from billing.models import WalletAccount
print(WalletAccount.objects.filter(available__gte=Decimal()))
for a in WalletAccount.objects.filter(available__gte=Decimal()):
	a.available = Decimal()
	a.current = Decimal()
	a.reserved = Decimal()
	a.uncleared = Decimal()
	a.save()

