from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key

def price_databricks(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = stripped(component.get("service"), "Azure Databricks")     # default Databricks service
    product = stripped(component.get("product"), None)                   # optional
    sku     = stripped(component.get("sku"), "") or ""                   # e.g., "DBU Standard", "DBU Premium"
    uom     = stripped(component.get("uom"), "1 DBU Hour") or None       # typical unit for Databricks
    qty     = decimal(component.get("quantity", 1))                      # quantity in DBUs
    hours   = decimal(component.get("hours_per_month", 1))               # set to 1 if qty already includes hours

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