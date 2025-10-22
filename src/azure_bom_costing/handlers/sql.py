from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..types import Key

def price_sql(component, region, currency, ent_prices: Dict[Key, Decimal]):
    # If your CSV uses "Azure SQL Database" or another exact string, pass service in component.
    service = (component.get("service") or "Azure SQL Database").strip()
    sku     = (component.get("sku") or "").strip()                  # e.g., GP_S_Gen5_4 or specific meter SKU name
    uom     = (component.get("uom") or "1 Hour").strip() or None    # vCore-hour commonly
    vcores  = decimal(component.get("vcores", component.get("instances", 1)))
    hours   = decimal(component.get("hours_per_month", 730))

    return price_by_service(
        service=service, sku=sku, region=region, currency=currency, ent_prices=ent_prices,
        uom=uom, qty=vcores, hours=hours, must_contain=[sku.lower()] if sku else None
    )