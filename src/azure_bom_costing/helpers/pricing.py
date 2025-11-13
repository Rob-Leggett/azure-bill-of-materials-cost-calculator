import logging
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple

from .csv import dedup_merge, arm_region, filter_rows, prefer_region, pick_first
from .math import decimal
from ..pricing.enterprise import enterprise_lookup
from ..pricing.retail import search_saved_retail_items, retail_fetch_items_live
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
        allowed_price_types: Optional[Set[str]] = None,  # defaults to {"Consumption","DevTestConsumption","Reservation"}
) -> Tuple[Decimal, str]:
    """
    Price a component using:
      1) Enterprise price (exact match on service, sku, region, uom)
      2) Retail fallback (saved JSON pages first, then live Retail API):
           - fetch by serviceName (regioned → global)
           - if still no match and `product` provided, fetch by productName (regioned → global)
      3) Filter rows:
           - exact equality on required columns
           - accept price type from priceType|type
           - optional UOM + token filters
           - prefer rows whose armRegionName matches the requested region
      4) Compute total = unit × qty × hours
    """
    logger.debug(
        "Starting price lookup: service=%s, sku=%s, region=%s, currency=%s",
        service,
        sku,
        region,
        currency,
    )

    # -------------------------------------------------------------------------
    # 1) Enterprise price (if available)
    # -------------------------------------------------------------------------
    ent = enterprise_lookup(ent_prices, service, sku, region, uom or "")
    if ent is not None:
        unit = decimal(ent)
        total = unit * qty * hours
        desc = f"{service} {sku} @{unit}/{uom or 'unit'} × {qty} × {hours}"
        logger.info(
            "Enterprise price hit for %s %s: unit=%s, total=%s, region=%s",
            service,
            sku,
            unit,
            total,
            region,
        )
        return total, desc

    # -------------------------------------------------------------------------
    # 2) Retail fallback (saved JSON pages → live API)
    # -------------------------------------------------------------------------
    arm = arm_region(region)
    logger.debug("No enterprise match; using retail fallback via ARM region '%s'", arm)

    # Build a list of increasingly broad filters.
    filters: List[str] = [
        f"serviceName eq '{service}' and armRegionName eq '{arm}'",
        f"serviceName eq '{service}'",
    ]
    if product:
        filters += [
            f"productName eq '{product}' and armRegionName eq '{arm}'",
            f"productName eq '{product}'",
        ]

    # First try searching locally saved JSON pages
    lists_from_saved: List[List[dict]] = []
    for fexpr in filters:
        rows = search_saved_retail_items(
            filter_expr=fexpr,
            currency=currency,
            # rely on later filters for positive price; we want full context here
            require_positive_price=False,
        )
        if rows:
            lists_from_saved.append(rows)

    if lists_from_saved:
        logger.debug(
            "Found %d filter result sets in saved pages for service=%s, product=%s",
            len(lists_from_saved),
            service,
            product,
        )
        items = dedup_merge(lists_from_saved)
    else:
        # Fallback to live Retail API if nothing found in saved pages
        logger.info(
            "No matching items found in saved retail pages for %s%s; "
            "falling back to live Retail API",
            service,
            f' / {product}' if product else "",
        )
        lists_from_live: List[List[dict]] = []
        for fexpr in filters:
            rows = retail_fetch_items_live(fexpr, currency)
            if rows:
                lists_from_live.append(rows)
        items = dedup_merge(lists_from_live) if lists_from_live else []

    logger.debug(
        "Total retail items after merge for %s%s: %d",
        service,
        f' / {product}' if product else "",
        len(items),
    )

    # -------------------------------------------------------------------------
    # 3) Filter candidate rows (priceType/type, UOM, tokens, region)
    # -------------------------------------------------------------------------
    if allowed_price_types is None:
        # Allow on-demand, dev/test, and reservations by default
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

    row = pick_first(rows)
    unit = decimal(row.get("retailPrice") or 0) if row else decimal(0)

    total = unit * qty * hours
    desc = (
        f"{service}{(' / ' + product) if product else ''} "
        f"{sku} @{unit}/{uom or 'unit'} × {qty} × {hours}"
    )

    logger.info(
        "Computed total for %s %s: unit=%s, total=%s, region=%s (rows=%d)",
        service,
        sku,
        unit,
        total,
        region,
        len(rows) if rows else 0,
    )
    return total, desc