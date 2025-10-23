from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key

def price_front_door(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = stripped(component.get("service"), "Azure Front Door")     # default service name
    product = stripped(component.get("product"), None)                   # optional
    sku     = stripped(component.get("sku"), "") or ""                   # e.g., "Standard", "Premium"
    uom     = stripped(component.get("uom"), "1 Hour") or None           # e.g., "1 Hour", "1 GB", etc.
    qty     = decimal(
        component.get(
            "quantity",
            component.get("instances", component.get("gb", component.get("requests_millions", 1)))
        )
    )
    hours   = decimal(component.get("hours_per_month", 730 if (uom or "").lower() == "1 hour" else 1))

    return price_by_service(
        service=service,
        product=product,
        sku=sku,
        region=region,
        currency=currency,
        ent_prices=ent_prices,
        uom=uom,
        qty=qty,
        hours=hours,
        must_contain=[sku.lower()] if sku else None,
    )