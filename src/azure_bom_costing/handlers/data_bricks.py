from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..types import Key

def price_databricks(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = "Azure Databricks"
    sku     = (component.get("sku") or "").strip()  # e.g., DBU tier
    uom     = (component.get("uom") or "").strip() or None
    qty     = decimal(component.get("quantity", 1))       # e.g., DBUs or hours × nodes; you pass qty
    hours   = decimal(component.get("hours_per_month", 1))  # set to 1 if qty already includes hours

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