from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..types import Key

def price_private_network(component, region, currency, ent_prices: Dict[Key, Decimal]):
    # Override service in component if your CSV uses "Private Link", "Virtual Network", etc.
    service = (component.get("service") or "Virtual Network").strip()
    sku     = (component.get("sku") or "").strip()                  # e.g., Private Link, Endpoints, PIP, etc.
    uom     = (component.get("uom") or "").strip() or None          # e.g., "1 Hour", "1 Gateway Hour"
    qty     = decimal(component.get("quantity", component.get("instances", 1)))
    hours   = decimal(component.get("hours_per_month", 730 if (uom or "").lower() == "1 hour" else 1))

    return price_by_service(
        service=service, sku=sku, region=region, currency=currency, ent_prices=ent_prices,
        uom=uom, qty=qty, hours=hours, must_contain=[sku.lower()] if sku else None
    )