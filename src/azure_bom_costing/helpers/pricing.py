from decimal import Decimal
from typing import Dict, List, Optional

from .rows import filter_rows, prefer_region, pick_first
from .csv import dedup_merge
from .math import decimal
from ..pricing.enterprise import enterprise_lookup
from ..pricing.retail import retail_fetch_items
from ..types import Key

def price_by_service(
        *,
        service: str,
        sku: str,
        region: str,
        currency: str,
        ent_prices: Dict[Key, Decimal],
        uom: Optional[str],
        qty: Decimal,
        hours: Decimal,
        must_contain: Optional[List[str]] = None,
        extra_required_equals: Optional[Dict[str, str]] = None,
) -> tuple[Decimal, str]:
    """
    One consistent pricing flow used by all handlers:
      1) Enterprise exact match (service, sku, region, uom)
      2) Retail fallback (two filters: regioned, then global)
      3) CSV-only row filter + region preference + first pick
      4) Multiply unit × qty × hours (hours can be 1 for non-hour UOMs)
    """
    # --- Enterprise first ---
    ent = enterprise_lookup(ent_prices, service, sku, region, uom or "")
    if ent is not None:
        unit = decimal(ent)
        total = unit * qty * hours
        desc  = f"{service} {sku} @{unit}/{uom or 'unit'} × {qty} × {hours}"
        return total, desc

    # --- Retail fallback ---
    filt_region = f"serviceName eq '{service}' and armRegionName eq '{region}' and priceType eq 'Consumption'"
    filt_global = f"serviceName eq '{service}' and priceType eq 'Consumption'"
    items = dedup_merge([retail_fetch_items(f, currency) for f in (filt_region, filt_global)])

    required_equals = {"serviceName": service, "priceType": "Consumption"}
    if extra_required_equals:
        required_equals.update(extra_required_equals)

    rows = filter_rows(
        items,
        required_equals=required_equals,
        required_uom=uom,
        must_contain=[t.lower() for t in (must_contain or []) if t],
    )
    rows = prefer_region(rows, region)
    row  = pick_first(rows)
    unit = decimal(row.get("retailPrice") or 0) if row else decimal(0)

    total = unit * qty * hours
    desc  = f"{service} {sku} @{unit}/{uom or 'unit'} × {qty} × {hours}"
    return total, desc