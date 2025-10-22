from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..types import Key

def price_front_door(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = (component.get("service") or "Azure Front Door").strip()
    sku     = (component.get("sku") or "").strip()   # e.g., Standard, Premium, Rules Engine, etc.
    uom     = (component.get("uom") or "").strip() or None  # could be '1 Hour' or '1 GB' (data transfer)
    qty     = decimal(component.get("quantity", component.get("instances", component.get("gb", 1))))
    hours   = decimal(component.get("hours_per_month", 730 if (uom or "").lower() == "1 hour" else 1))

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