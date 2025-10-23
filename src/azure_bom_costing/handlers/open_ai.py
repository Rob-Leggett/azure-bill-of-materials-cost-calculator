from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key

def price_open_ai(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = stripped(component.get("service"), "Cognitive Services")     # Azure OpenAI lives under this in CSV
    product = stripped(component.get("product"), "Azure OpenAI")           # product fallback for clarity
    sku     = stripped(component.get("sku"), "") or ""                     # e.g., "gpt-4o", "gpt-4.1-dev-ft ..."
    uom     = stripped(component.get("uom"), "1K") or None                 # e.g., "1K", "1 Image", "1 Hour"
    qty     = decimal(component.get("quantity", component.get("tokens_1k", component.get("images", 1))))
    hours   = decimal(component.get("hours_per_month", 1))                 # token/image-based → hours = 1

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