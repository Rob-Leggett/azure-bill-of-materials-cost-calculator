from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key

def price_data_factory(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = stripped(component.get("service"), "Data Factory")            # default service name
    product = stripped(component.get("product"), None)                      # optional
    sku     = stripped(component.get("sku"), "") or ""                      # e.g., "Pipeline Activity", "SSIS Hours"
    uom     = stripped(component.get("uom"), "1 Hour") or None              # commonly per hour or per 1,000 runs
    qty     = decimal(component.get("quantity", 1))                         # quantity of runs, executions, or hours
    hours   = decimal(component.get("hours_per_month", 1))                  # often explicit, may stay at 1 for unit

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