from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..types import Key

def price_container_apps(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = "Container Apps"
    sku     = (component.get("sku") or "").strip()   # if SKU-less, leave blank
    uom     = (component.get("uom") or "").strip() or None
    qty     = decimal(component.get("quantity", component.get("instances", 1)))
    hours   = decimal(component.get("hours_per_month", 730))

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