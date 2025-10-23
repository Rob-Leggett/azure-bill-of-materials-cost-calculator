from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key

def price_dev_ops(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = stripped(component.get("service"), "DevOps")              # default service name
    product = stripped(component.get("product"), None)                  # optional
    sku     = stripped(component.get("sku"), "") or ""                  # e.g., "User Basic", "Pipeline", etc.
    uom     = stripped(component.get("uom"), "1 User/Month") or None    # typically per-user or per-pipeline
    qty     = decimal(component.get("quantity", 1))                     # default to 1 if not provided
    hours   = decimal(component.get("hours_per_month", 1))              # per-month billing → hours=1

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