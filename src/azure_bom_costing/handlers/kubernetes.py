from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key

def price_kubernetes(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = stripped(component.get("service"), "Kubernetes Service")      # default AKS service name
    product = stripped(component.get("product"), None)
    sku     = stripped(component.get("sku"), "") or ""                      # e.g., "Uptime SLA", "Control Plane"
    uom     = stripped(component.get("uom"), "1 Hour") or None              # typical AKS billing unit
    qty     = decimal(component.get("quantity", component.get("clusters", component.get("instances", 1))))
    hours   = decimal(component.get("hours_per_month", 730))                # hourly metering by default

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