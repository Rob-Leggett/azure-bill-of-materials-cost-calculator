from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..types import Key

def price_functions(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = (component.get("service") or "Functions").strip()
    sku     = (component.get("sku") or "").strip()   # e.g., Consumption, Premium, Executions, GB-s
    uom     = (component.get("uom") or "").strip() or None  # e.g., '1 Million', '1 GB-s'
    qty     = decimal(component.get("quantity", component.get("executions", component.get("gb_seconds", 1))))
    hours   = decimal(component.get("hours_per_month", 1))  # non-hourly metering common

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