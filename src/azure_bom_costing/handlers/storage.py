from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key

def price_storage(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = stripped(component.get("service"), "Storage")
    product = stripped(component.get("product"), None)
    sku     = stripped(component.get("sku"), "") or ""                 # e.g. "Standard LRS Hot", "Archive GRS"
    uom     = stripped(component.get("uom"), None)                     # e.g. "1 GB/Month", "10,000", "1 Hour"

    # Quantity source (GB/TB/ops), prioritising explicit quantity -> gb -> tb -> ops
    qty = decimal(
        component.get(
            "quantity",
            component.get(
                "gb",
                component.get(
                    "tb",
                    component.get("operations_per_month", 1),
                ),
            ),
        )
    )

    # Convert TB → GB if UOM is GB-based and gb not already provided
    if "tb" in component and "gb" not in component:
        uom_l = (uom or "").lower()
        if "gb" in uom_l:
            qty = decimal(component["tb"]) * decimal(1024)

    # Hours: storage is monthly unless explicitly hourly
    hours = decimal(component.get("hours_per_month", 1 if (uom or "").lower() != "1 hour" else 730))

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