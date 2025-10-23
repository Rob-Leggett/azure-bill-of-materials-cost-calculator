from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key

def price_key_vault(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = stripped(component.get("service"), "Key Vault")               # Azure default service name
    product = stripped(component.get("product"), None)
    sku     = stripped(component.get("sku"), "") or ""                      # e.g., "Standard", "Premium"
    uom     = stripped(component.get("uom"), "10,000 Operations") or None   # typical metering unit
    qty     = decimal(component.get("quantity", component.get("operations", 1)))
    hours   = decimal(component.get("hours_per_month", 1))                  # per op or per month basis

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