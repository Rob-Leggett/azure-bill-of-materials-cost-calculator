from decimal import Decimal, ROUND_HALF_UP

def money(v) -> Decimal:
    """Quantise a numeric value to 2 decimal places using ROUND_HALF_UP.

    Appropriate for currency values (e.g., AUD).
    """
    return Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def decimal(val, default=Decimal(0)) -> Decimal:
    """Coerce a value to Decimal safely, with a default on failure.

    Accepts Decimal, int, float, str. Falls back to 'default' if parsing fails.
    """
    if isinstance(val, Decimal):
        return val
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal(default)