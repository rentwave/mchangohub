from decimal import Decimal, ROUND_HALF_UP

def check_pesaway_withdrawal_charges(amount_kes: float, available=None):
    """
    Check if a withdrawal can be made considering Pesaway tiered charges.

    Charge Tiers (KES):
        1 - 1,500         -> 12
        1,501 - 5,000     -> 19
        5,001 - 10,000    -> 24
        10,001 - 20,000   -> 33
        20,001 - 250,000  -> 39

    Returns:
        dict with:
            can_withdraw (bool)
            charge (Decimal)
            withdrawable (Decimal)
    """
    amount = Decimal(str(amount_kes))
    available = Decimal(str(available)) if available else Decimal("0")
    tiers = [
        (Decimal("1"), Decimal("1500"), Decimal("12")),
        (Decimal("1501"), Decimal("5000"), Decimal("19")),
        (Decimal("5001"), Decimal("10000"), Decimal("24")),
        (Decimal("10001"), Decimal("20000"), Decimal("33")),
        (Decimal("20001"), Decimal("250000"), Decimal("39")),
    ]
    charge = Decimal("0")
    for min_limit, max_limit, fee in tiers:
        if min_limit <= amount <= max_limit:
            charge = fee
            break
    if charge == 0:
        charge = tiers[-1][2]
    withdrawable = (amount - charge).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    can_withdraw = available >= withdrawable
    if amount_kes > withdrawable:
        can_withdraw = False
    print(f"[DEBUG] Withdrawable: {withdrawable}, Charge: {charge}, Available: {available}, Allowed: {can_withdraw}")
    return {
        "can_withdraw": can_withdraw,
        "charge": charge,
        "withdrawable": withdrawable,
    }

can_withdraw = check_pesaway_withdrawal_charges(amount_kes=15, available=17)
print(can_withdraw)
