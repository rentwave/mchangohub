from decimal import Decimal

from billing.models import WalletAccount

for a in WalletAccount.objects.filter(available__gt=Decimal()):
	a.available = Decimal()
	a.current = Decimal()
	a.reserved = Decimal()
	a.uncleared = Decimal()
	a.save()

