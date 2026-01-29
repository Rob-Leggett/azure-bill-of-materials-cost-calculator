from decimal import Decimal
from typing import Any

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key


def price_automation(
    component: dict[str, Any],
    region: str,
    currency: str,
    ent_prices: dict[Key, Decimal],
) -> tuple[Decimal, str]:
    """Price Azure Automation based on job minutes."""
    service = stripped(component.get("service"), "Automation")
    product = stripped(component.get("product"), None)
    sku = stripped(component.get("sku"), None)
    uom = stripped(component.get("uom"), None)
    qty = decimal(component.get("quantity"), Decimal(0))
    hours = decimal(component.get("hours_per_month"), Decimal(1))

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
