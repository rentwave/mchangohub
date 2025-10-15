from base.models import State
from billing.models import WalletTransaction
state_pending = State.objects.get(name='Pending')
print(WalletTransaction.objects.get(
	reference="A0H5NTKUYW1760541111",
                transaction_type='payment',
                status=state_pending))