from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key

def price_log_analytics(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = stripped(component.get("service"), "Log Analytics")        # default Azure service name
    product = stripped(component.get("product"), None)                   # optional
    sku     = stripped(component.get("sku"), "") or ""                   # e.g., "Per GB", "Per Node", "Retention"
    uom     = stripped(component.get("uom"), "1 GB") or None             # common billing unit
    qty     = decimal(component.get("quantity", component.get("gb", component.get("nodes", 1))))
    hours   = decimal(component.get("hours_per_month", 1))               # non-hourly, defaults to monthly (1)

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
        must_contain=[sku.lower()] if sku else None
    )