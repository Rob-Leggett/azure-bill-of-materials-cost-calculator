from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..types import Key

def price_open_ai(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = (component.get("service") or "Azure OpenAI").strip()
    sku     = (component.get("sku") or "").strip()                  # e.g., model/rate card code
    uom     = (component.get("uom") or "").strip() or None          # e.g., "1,000 Tokens", "1 Image", "1 Hour"
    qty     = decimal(component.get("quantity", component.get("tokens_1k", component.get("images", 1))))
    hours   = decimal(component.get("hours_per_month", 1))          # token/image priced → hours=1

    return price_by_service(
        service=service, sku=sku, region=region, currency=currency, ent_prices=ent_prices,
        uom=uom, qty=qty, hours=hours, must_contain=[sku.lower()] if sku else None
    )