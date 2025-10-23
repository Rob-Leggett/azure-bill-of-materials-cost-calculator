from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key

def price_sql(component, region, currency, ent_prices: Dict[Key, Decimal]):
    # If your CSV uses "Azure SQL Database" or another exact string, pass service in component.
    service = stripped(component.get("service"), "SQL Database")
    product = stripped(component.get("product"), None)
    sku     = stripped(component.get("sku"), "") or ""               # e.g., GP_S_Gen5_4 or specific meter SKU
    uom     = stripped(component.get("uom"), "1 Hour") or None       # typically per vCore-hour
    qty     = decimal(component.get("quantity", component.get("vcores", component.get("instances", 1))))
    hours   = decimal(component.get("hours_per_month", 730))

    return price_by_service(
        service=service,
        product=product,
        sku=sku,
        region=region,
        currency=currency,
        ent_prices=ent_prices,
        uom=uom,
        qty=vcores,
        hours=hours,
        must_contain=[sku.lower()] if sku else None
    )