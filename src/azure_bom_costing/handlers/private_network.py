from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key

def price_private_network(component, region, currency, ent_prices: Dict[Key, Decimal]):
    # Override service in component if your CSV uses "Private Link", "Virtual Network", etc.
    service = stripped(component.get("service"), "Virtual Network")     # common Azure name for networking
    product = stripped(component.get("product"), None)
    sku     = stripped(component.get("sku"), "") or ""                  # e.g., "Private Link", "Endpoints", "PIP"
    uom     = stripped(component.get("uom"), "") or None                # e.g., "1 Hour", "1 Gateway Hour"
    qty     = decimal(component.get("quantity", component.get("instances", 1)))

    # Default billing hours: 730 if hourly UOM, otherwise 1 (monthly)
    uom_l = (uom or "").lower()
    hours = decimal(component.get("hours_per_month", 730 if "hour" in uom_l else 1))

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