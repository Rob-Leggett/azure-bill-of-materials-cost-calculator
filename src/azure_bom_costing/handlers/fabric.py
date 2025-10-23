from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key

def price_fabric(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = stripped(component.get("service"), "Microsoft Fabric")      # default service name
    product = stripped(component.get("product"), None)                    # optional
    sku     = stripped(component.get("sku"), "") or ""                    # e.g., "F64", "F128"
    uom     = stripped(component.get("uom"), "1 Hour") or None            # typically "1 Hour" or "1 CU Hour"
    qty     = decimal(component.get("quantity", component.get("capacity_units", 1)))
    hours   = decimal(component.get("hours_per_month", 730))              # capacity billed hourly

    return price_by_service(
        service=service,
        product=product,
        sku=sku,
        region=region,   # may be global, still safe
        currency=currency,
        ent_prices=ent_prices,
        uom=uom,
        qty=qty,
        hours=hours,
        must_contain=[sku.lower()] if sku else None,
    )