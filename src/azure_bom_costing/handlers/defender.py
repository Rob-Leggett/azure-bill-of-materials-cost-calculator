from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key

def price_defender(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = stripped(component.get("service"), "Microsoft Defender")   # default service family
    product = stripped(component.get("product"), None)                   # optional
    sku     = stripped(component.get("sku"), "") or ""                   # e.g., "Servers P1", "Servers P2"
    uom     = stripped(component.get("uom"), "1 Node/Month") or None     # typically per node or resource per month
    qty     = decimal(component.get("quantity", 1))                      # number of protected resources
    hours   = decimal(component.get("hours_per_month", 1))               # monthly pricing → hours=1

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