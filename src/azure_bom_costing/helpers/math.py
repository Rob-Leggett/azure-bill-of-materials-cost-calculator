from decimal import ROUND_HALF_UP, Decimal
from typing import Any


def money(v: Any) -> Decimal:
    """Quantise a numeric value to 2 decimal places using ROUND_HALF_UP.

    Appropriate for currency values (e.g., AUD).
    """
    return Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def decimal(val: Any, default: Any = Decimal(0)) -> Decimal:
    """Coerce a value to Decimal safely, with a default on failure.

    Accepts Decimal, int, float, str. Falls back to 'default' if parsing fails.
    """
    if isinstance(val, Decimal):
        return val
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal(default)