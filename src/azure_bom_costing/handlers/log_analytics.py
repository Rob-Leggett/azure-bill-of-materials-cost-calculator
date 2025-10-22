from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..types import Key

def price_log_analytics(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = (component.get("service") or "Log Analytics").strip()
    sku     = (component.get("sku") or "").strip()                  # e.g., Per GB, Per Node, Retention, etc.
    uom     = (component.get("uom") or "").strip() or None          # e.g., "1 GB", "1 Node/Month"
    qty     = decimal(component.get("quantity", component.get("gb", component.get("nodes", 1))))
    hours   = decimal(component.get("hours_per_month", 1))          # commonly non-hourly; set to 1 by default

    return price_by_service(
        service=service, sku=sku, region=region, currency=currency, ent_prices=ent_prices,
        uom=uom, qty=qty, hours=hours, must_contain=[sku.lower()] if sku else None
    )