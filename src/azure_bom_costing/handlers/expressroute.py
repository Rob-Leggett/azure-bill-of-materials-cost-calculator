from decimal import Decimal
from typing import Any

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key


def price_expressroute(
    component: dict[str, Any],
    region: str,
    currency: str,
    ent_prices: dict[Key, Decimal],
) -> tuple[Decimal, str]:
    """Price ExpressRoute circuits based on SKU (bandwidth) and hours."""
    service = stripped(component.get("service"), "ExpressRoute")
    product = stripped(component.get("product"), None)
    sku = stripped(component.get("sku"), None)
    uom = stripped(component.get("uom"), "1 Hour")
    qty = decimal(component.get("circuits", component.get("quantity")), Decimal(1))
    hours = decimal(component.get("hours_per_month"), Decimal(730))

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
