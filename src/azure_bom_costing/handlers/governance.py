from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key

def price_governance(component, region, currency, ent_prices: Dict[Key, Decimal]):
    # Leaving service name overridable to match your CSV exactly (could be 'Policy', 'Cost Management', etc.)
    service = stripped(component.get("service"), "Governance")          # default high-level service name
    product = stripped(component.get("product"), None)                  # optional
    sku     = stripped(component.get("sku"), "") or ""                  # e.g., "Policy Assessment", "Blueprints"
    uom     = stripped(component.get("uom"), "1 Unit") or None          # often "1 Unit" or similar metric
    qty     = decimal(component.get("quantity", 1))                     # usually monthly event count
    hours   = decimal(component.get("hours_per_month", 1))              # billed per month by default

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