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

    Rules:
        - Find applicable charge based on amount.
        - A withdrawal is allowed only if:
            1. amount > charge
            2. withdrawable > 0
            3. (amount + charge) <= available
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

    # Determine applicable charge
    charge = Decimal("0")
    for min_limit, max_limit, fee in tiers:
        if min_limit <= amount <= max_limit:
            charge = fee
            break
    if charge == 0:
        charge = tiers[-1][2]

    # Withdrawable = what the user will actually receive
    withdrawable = (amount - charge).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Fixed logic: must meet all 3 conditions
    can_withdraw = (
        amount > charge and
        withdrawable > 0 and
        (amount + charge) <= available
    )

    print(
        f"[DEBUG] Amount: {amount}, Charge: {charge}, Total Required: {amount + charge}, "
        f"Available: {available}, Withdrawable: {withdrawable}, Allowed: {can_withdraw}"
    )

    return {
        "can_withdraw": can_withdraw,
        "charge": charge,
        "withdrawable": withdrawable,
    }

# Test cases
print("\nTest 1: amount=4, available=17")
print(check_pesaway_withdrawal_charges(amount_kes=4, available=17))

print("\nTest 2: amount=15, available=17")
print(check_pesaway_withdrawal_charges(amount_kes=15, available=17))

print("\nTest 3: amount=2000, available=2050")
print(check_pesaway_withdrawal_charges(amount_kes=2040, available=2050))
