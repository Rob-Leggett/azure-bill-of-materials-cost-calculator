from decimal import Decimal
from typing import Dict

from ..helpers.math import decimal
from ..helpers.pricing import price_by_service
from ..helpers.string import stripped
from ..types import Key

def price_app_insights(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = stripped(component.get("service"), "Application Insights")    # default to Application Insights
    product = stripped(component.get("product"), None)                      # optional
    sku     = stripped(component.get("sku"), "") or ""                      # e.g., "Ingest", "Data Retention", etc.
    uom     = stripped(component.get("uom"), "1 GB") or None                # typically "1 GB" or "1 GB/Month"
    qty     = decimal(component.get("quantity", component.get("gb", 1)))    # ingestion volume in GB
    hours   = decimal(component.get("hours_per_month", 1))                  # non-hourly → 1

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