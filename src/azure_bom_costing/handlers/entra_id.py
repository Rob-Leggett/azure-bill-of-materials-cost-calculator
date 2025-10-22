from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..types import Key

def price_entra_id(component, region, currency, ent_prices: Dict[Key, Decimal]):
    # Depending on your CSV, this might still be 'Azure Active Directory' or 'Microsoft Entra ID'.
    service = (component.get("service") or "Microsoft Entra ID").strip()
    sku     = (component.get("sku") or "").strip()   # e.g., P1, P2, External Identities, etc.
    uom     = (component.get("uom") or "").strip() or None  # often '1 Month' or '1 User/Month'
    qty     = decimal(component.get("quantity", component.get("users", 1)))
    hours   = decimal(component.get("hours_per_month", 1))  # monthly/user pricing → hours=1

    return price_by_service(
        service=service,
        sku=sku,
        region=region,   # region may be ignored by directory SKUs, still safe to pass
        currency=currency,
        ent_prices=ent_prices,
        uom=uom,
        qty=qty,
        hours=hours,
        must_contain=[sku.lower()] if sku else None,
    )