import logging
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple

from .csv import dedup_merge, arm_region, filter_rows, prefer_region, pick_first
from .math import decimal
from ..pricing.enterprise import enterprise_lookup
from ..pricing.retail import retail_fetch_items
from ..types import Key

logger = logging.getLogger(__name__)

def price_by_service(
        *,
        service: str,
        product: Optional[str] = None,
        sku: str,
        region: str,
        currency: str,
        ent_prices: Dict[Key, Decimal],
        uom: Optional[str],
        qty: Decimal,
        hours: Decimal,
        must_contain: Optional[List[str]] = None,
        extra_required_equals: Optional[Dict[str, str]] = None,
        allowed_price_types: Optional[Set[str]] = None,  # defaults to {"Consumption","DevTestConsumption"}
) -> Tuple[Decimal, str]:
    """
    1) Enterprise exact match (service, sku, region, uom)
    2) Retail fallback:
         - fetch by serviceName (regioned → global)
         - if still no match and 'product' provided, fetch by productName (regioned → global)
    3) CSV filter: accept price type from priceType|type; prefer region; first pick
    4) Compute total = unit × qty × hours
    """
    logger.debug(f"Starting price lookup: service={service}, sku={sku}, region={region}, currency={currency}")

    # ---------- Enterprise price ----------
    ent = enterprise_lookup(ent_prices, service, sku, region, uom or "")
    if ent is not None:
        unit = decimal(ent)
        total = unit * qty * hours
        desc  = f"{service} {sku} @{unit}/{uom or 'unit'} × {qty} × {hours}"
        return total, desc

    # ---------- Retail fallback ----------
    arm = arm_region(region)
    logger.debug(f"No enterprise match found, using retail fallback via ARM region '{arm}'")

    # Be permissive in fetch (some CSVs leave 'priceType' blank and only set 'type')
    filters: List[str] = [
        f"serviceName eq '{service}' and armRegionName eq '{arm}'",
        f"serviceName eq '{service}'",
    ]
    if product:
        filters += [
            f"productName eq '{product}' and armRegionName eq '{arm}'",
            f"productName eq '{product}'",
        ]

    items = dedup_merge([retail_fetch_items(f, currency) for f in filters])
    logger.debug(f"Fetched {len(items)} retail items for {service}{' / ' + product if product else ''}")

    # Defaults: allow on-demand + dev/test, Reservation
    if allowed_price_types is None:
        allowed_price_types = {"Consumption", "DevTestConsumption", "Reservation"}

    tokens = [t.lower() for t in (must_contain or []) if t]

    def _filter(required_eq: Dict[str, str]) -> List[dict]:
        rows = filter_rows(
            items,
            required_equals=required_eq,
            required_uom=uom,
            must_contain=tokens,
            allowed_price_types=allowed_price_types,
            region_hint=region,
        )
        return prefer_region(rows, region)

    # First pass: serviceName
    required_equals = {"serviceName": service}
    if extra_required_equals:
        required_equals.update(extra_required_equals)
    rows = _filter(required_equals)

    # Fallback: productName (ONLY if product provided)
    if not rows and product:
        rows = _filter({"productName": product})

    row  = pick_first(rows)
    unit = decimal(row.get("retailPrice") or 0) if row else decimal(0)

    total = unit * qty * hours
    desc  = f"{service}{(' / ' + product) if product else ''} {sku} @{unit}/{uom or 'unit'} × {qty} × {hours}"
    logger.info(f"Computed total for {service} {sku}: unit={unit}, total={total}, region={region}")
    return total, desc