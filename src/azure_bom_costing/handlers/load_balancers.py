from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key

def price_load_balancers(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = stripped(component.get("service"), None)
    product = stripped(component.get("product"), None)
    sku     = stripped(component.get("sku"), None)
    uom     = stripped(component.get("uom"), None)
    qty     = decimal(component.get("quantity"), None)
    hours   = decimal(component.get("hours_per_month"), None)

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
        must_contain=[sku.lower()] if sku else None
    )