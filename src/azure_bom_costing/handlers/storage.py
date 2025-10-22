from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..types import Key

def price_storage(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = (component.get("service") or "Storage").strip()
    sku     = (component.get("sku") or "").strip()                  # e.g., LRS Hot, ZRS Cool, Queue, Table, etc.
    uom     = (component.get("uom") or "").strip() or None          # e.g., "1 GB/Month", "10,000", "1 Hour"
    qty     = decimal(component.get("quantity",
                                    component.get("gb", component.get("tb", component.get("operations_per_month", 1)))))
    # If TB given, pass quantity in GB to match "1 GB/Month" UoM.
    if "tb" in component and ("gb" not in component) and (uom or "").lower() == "1 gb/month":
        qty = decimal(component["tb"]) * decimal(1024)

    hours   = decimal(component.get("hours_per_month", 1 if (uom or "").lower() != "1 hour" else 730))

    return price_by_service(
        service=service, sku=sku, region=region, currency=currency, ent_prices=ent_prices,
        uom=uom, qty=qty, hours=hours, must_contain=[sku.lower()] if sku else None
    )