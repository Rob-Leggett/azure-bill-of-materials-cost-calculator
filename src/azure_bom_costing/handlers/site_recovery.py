from decimal import Decimal
from typing import Any

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key


def price_site_recovery(
    component: dict[str, Any],
    region: str,
    currency: str,
    ent_prices: dict[Key, Decimal],
) -> tuple[Decimal, str]:
    """Price Azure Site Recovery based on protected instances."""
    service = stripped(component.get("service"), "Site Recovery")
    product = stripped(component.get("product"), "Azure Site Recovery")
    sku = stripped(component.get("sku"), None)
    uom = stripped(component.get("uom"), "1/Month")
    qty = decimal(
        component.get("protected_vms", component.get("quantity")), Decimal(1)
    )
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
        must_contain=["site recovery"] if not sku else [sku.lower()],
    )
