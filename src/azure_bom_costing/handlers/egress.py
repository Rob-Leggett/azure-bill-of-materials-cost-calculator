from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key

def price_egress(component, region, currency, ent_prices: Dict[Key, Decimal]):
    # Azure retail often uses 'Bandwidth' as the service for egress.
    service = stripped(component.get("service"), "Bandwidth")             # default for Azure egress
    product = stripped(component.get("product"), None)                    # optional
    sku     = stripped(component.get("sku"), "") or ""                    # e.g., "Zone1 Internet"
    uom     = stripped(component.get("uom"), "1 GB") or None              # typically per GB
    qty     = decimal(component.get("quantity", component.get("gb", 0)))  # use GB for quantity
    hours   = decimal(component.get("hours_per_month", 1))                # non-hourly, per GB basis


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