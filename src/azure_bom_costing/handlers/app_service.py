from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key

def price_app_service(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = stripped(component.get("service"), "App Service")            # default to App Service
    product = stripped(component.get("product"), None)                     # optional
    sku     = stripped(component.get("sku"), "") or ""                     # e.g., "P1v4", "B1", etc.
    uom     = stripped(component.get("uom"), "1 Hour") or None             # typical for compute plans
    qty     = decimal(component.get("quantity", component.get("instances", 1)))  # instance count
    hours   = decimal(component.get("hours_per_month", 730))               # compute hours per month


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