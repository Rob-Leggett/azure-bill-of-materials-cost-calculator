from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key

def price_entra_id(component, region, currency, ent_prices: Dict[Key, Decimal]):
    # Depending on your CSV, this might still be 'Azure Active Directory' or 'Microsoft Entra ID'.
    service = stripped(component.get("service"), "Microsoft Entra ID")   # default service name
    product = stripped(component.get("product"), None)                   # optional
    sku     = stripped(component.get("sku"), "") or ""                   # e.g., "P1", "P2"
    uom     = stripped(component.get("uom"), "1 User/Month") or None     # typical per-user monthly billing
    qty     = decimal(component.get("quantity", component.get("users", 1)))
    hours   = decimal(component.get("hours_per_month", 1))               # monthly pricing → hours=1

    return price_by_service(
        service=service,
        product=product,
        sku=sku,
        region=region,   # region may be ignored by directory SKUs, still safe to pass
        currency=currency,
        ent_prices=ent_prices,
        uom=uom,
        qty=qty,
        hours=hours,
        must_contain=[sku.lower()] if sku else None,
    )