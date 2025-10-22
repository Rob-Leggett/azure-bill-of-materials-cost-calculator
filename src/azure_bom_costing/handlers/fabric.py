from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..types import Key

def price_fabric(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = (component.get("service") or "Microsoft Fabric").strip()
    sku     = (component.get("sku") or "").strip()   # e.g., F SKUs / capacity units
    uom     = (component.get("uom") or "").strip() or None  # e.g., '1 CU Hour' / '1 Hour'
    qty     = decimal(component.get("quantity", component.get("capacity_units", 1)))
    hours   = decimal(component.get("hours_per_month", 730))  # adjust if UoM already hourly in qty

    return price_by_service(
        service=service,
        sku=sku,
        region=region,   # may be global, still safe
        currency=currency,
        ent_prices=ent_prices,
        uom=uom,
        qty=qty,
        hours=hours,
        must_contain=[sku.lower()] if sku else None,
    )