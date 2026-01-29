from decimal import Decimal
from typing import Any

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key


def price_sentinel(
    component: dict[str, Any],
    region: str,
    currency: str,
    ent_prices: dict[Key, Decimal],
) -> tuple[Decimal, str]:
    """Price Microsoft Sentinel based on GB ingested."""
    service = stripped(component.get("service"), "Sentinel")
    product = stripped(component.get("product"), "Microsoft Sentinel")
    sku = stripped(component.get("sku"), None)
    uom = stripped(component.get("uom"), "1 GB")
    qty = decimal(component.get("gb", component.get("quantity")), Decimal(0))
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
        must_contain=["sentinel"] if not sku else [sku.lower()],
    )
