from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key

def price_backup(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = stripped(component.get("service"), "Backup")                 # default Azure Backup service
    product = stripped(component.get("product"), None)                     # optional product
    sku     = stripped(component.get("sku"), "") or ""                     # e.g., "Protected Instance", "Vault Tier"
    uom     = stripped(component.get("uom"), "1 GB/Month") or None         # typical UOM for storage-based billing
    qty     = decimal(component.get("quantity", 1))                        # protected instances or storage amount
    hours   = decimal(component.get("hours_per_month", 1))                 # monthly billing → hours=1

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