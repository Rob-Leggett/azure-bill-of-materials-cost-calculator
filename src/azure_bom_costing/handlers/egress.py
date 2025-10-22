from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..types import Key

def price_egress(component, region, currency, ent_prices: Dict[Key, Decimal]):
    # Azure retail often uses 'Bandwidth' as the service for egress.
    service = (component.get("service") or "Bandwidth").strip()
    sku     = (component.get("sku") or "").strip()   # e.g., Zone1/Zone2/Internet Egress tier
    uom     = (component.get("uom") or "").strip() or None  # e.g., '1 GB'
    qty     = decimal(component.get("quantity", component.get("gb", 0)))  # pass GB in quantity
    hours   = decimal(component.get("hours_per_month", 1))  # GB-based pricing → hours=1

    return price_by_service(
        service=service,
        sku=sku,
        region=region,
        currency=currency,
        ent_prices=ent_prices,
        uom=uom,
        qty=qty,
        hours=hours,
        must_contain=[sku.lower()] if sku else None,
    )