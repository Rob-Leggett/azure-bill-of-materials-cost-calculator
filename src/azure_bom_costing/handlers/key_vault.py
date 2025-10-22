from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..types import Key

def price_key_vault(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = (component.get("service") or "Key Vault").strip()
    sku     = (component.get("sku") or "").strip()   # e.g., Standard/Premium, operations, secrets ops, etc.
    uom     = (component.get("uom") or "").strip() or None  # e.g., '10,000 operations', '1 Key/Month'
    qty     = decimal(component.get("quantity", component.get("operations", 1)))
    hours   = decimal(component.get("hours_per_month", 1))  # usually per op or per month

    return price_by_service(
        service=service,
        sku=sku,
        region=region,
        currency=currency,
        ent_prices=ent_prices,
        uom=uom,
        qty=qty,
        hours=hours,
        must_contain=[sku.lower()] if sku else None,
    )