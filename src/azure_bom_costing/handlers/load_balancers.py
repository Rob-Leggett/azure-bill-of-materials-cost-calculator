from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..types import Key

def price_load_balancers(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = (component.get("service") or "Load Balancer").strip()
    sku     = (component.get("sku") or "").strip()                  # e.g., Basic/Standard rules, data processed
    uom     = (component.get("uom") or "").strip() or None          # e.g., "1 Hour", "1 GB", "1 Rule Hour"
    qty     = decimal(component.get("quantity", component.get("instances", component.get("gb", 1))))
    hours   = decimal(component.get("hours_per_month", 730 if (uom or "").lower() == "1 hour" else 1))

    return price_by_service(
        service=service, sku=sku, region=region, currency=currency, ent_prices=ent_prices,
        uom=uom, qty=qty, hours=hours, must_contain=[sku.lower()] if sku else None
    )