from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key

def price_load_balancers(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = stripped(component.get("service"), "Load Balancer")           # Azure service name
    product = stripped(component.get("product"), None)                      # optional
    sku     = stripped(component.get("sku"), "") or ""                      # e.g., "Standard Rule Hour", "Data Processed"
    uom     = stripped(component.get("uom"), "1 Hour") or None              # e.g., "1 Hour", "1 GB"
    qty     = decimal(component.get("quantity", component.get("instances", component.get("gb", 1))))

    # Default billing hours: 730 if hourly, otherwise monthly (1)
    uom_l = (uom or "").lower()
    hours = decimal(component.get("hours_per_month", 730 if "hour" in uom_l else 1))

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