# =====================================================================================
# Azure Cache for Redis. Example component:
# {
#   "type": "redis",
#   "sku": "C1",
#   "instances": 1,
#   "hours_per_month": 730
# }
#
# Notes:
# • `sku` – Redis cache tier:
#     - C-series = Basic/Standard (C0–C6)
#     - P-series = Premium (P1–P5)
#     - E-series = Enterprise/Enterprise Flash (E10, E20, etc.)
# • `instances` – Number of Redis cache instances of the given tier.
# • `hours_per_month` – Runtime duration (default 730 hours for full-month uptime).
# • Enterprise pricing is matched first; otherwise retail rates are fetched from Azure API.
# • Billing unit: “1 Hour”.
# • Common usage: caching sessions, tokens, or app data for web/API workloads.
# =====================================================================================
from decimal import Decimal
from typing import Dict, List

from ..helpers import _d, _arm_region, _pick, _dedup_merge
from ..pricing_sources import enterprise_lookup, retail_fetch_items
from ..types import Key

def _redis_family_for_sku(sku: str) -> str:
    s = sku.upper()
    if s.startswith("P"):
        return "premium"
    if s.startswith("E"):
        return "enterprise"   # will also match Enterprise Flash by word 'enterprise'
    return "c"  # C-series: Basic/Standard


def _txt(i: dict) -> str:
    return " ".join([
        i.get("serviceName", ""),
        i.get("productName", ""),
        i.get("skuName", ""),
        i.get("meterName", "")
    ]).lower()


def _is_bad_redis_row(i: dict) -> bool:
    t = _txt(i)
    # Non-instance or unrelated meters we should ignore
    bad = [
        "data transfer", "bandwidth", "outbound", "inbound",
        "backup", "snapshot", "operations", "private link",
        "virtual network", "dns", "gateway", "metered feature"
    ]
    return any(b in t for b in bad)


def _score_redis_row(i: dict, arm_region: str, sku_token: str, fam: str) -> int:
    if _d(i.get("retailPrice", 0)) <= 0 or _is_bad_redis_row(i):
        return -999

    t = _txt(i)
    s = 0
    # Core signals
    if (i.get("unitOfMeasure") or "") == "1 Hour": s += 6
    if (i.get("armRegionName") or "").lower() == arm_region: s += 5
    if "redis" in t: s += 3

    # SKU token like 'c2', 'p1', 'e10'
    if sku_token in t.replace(" ", ""):  # handle "C 2" variants
        s += 6
    elif sku_token in t:
        s += 4

    # Family / tier signals
    if fam == "premium" and "premium" in t: s += 4
    if fam == "enterprise" and "enterprise" in t: s += 4
    if fam == "c":
        # Prefer Standard to Basic if both appear, but accept either
        if "standard" in t: s += 3
        if "basic" in t: s += 2

    # Additional helpful tokens
    if "cache" in t: s += 1
    return s


def price_redis(component, region, currency, ent_prices: Dict[Key, Decimal]):
    sku = component.get("sku", "C1").upper()  # C1|C2|P1|P2|E10...
    inst = _d(component.get("instances", 1))
    hours = _d(component.get("hours_per_month", 730))
    service, uom = "Azure Cache for Redis", "1 Hour"

    # Enterprise first
    ent = enterprise_lookup(ent_prices, service, sku, region, uom)
    if ent is not None:
        unit = ent
    else:
        arm = _arm_region(region)
        fam = _redis_family_for_sku(sku)       # "c" | "premium" | "enterprise"
        sku_token = sku.lower()                # e.g. "c2", "p1", "e10"

        # Build robust filters (regioned + global, wide wording)
        filters: List[str] = [
            # Regioned precise
            (f"serviceName eq 'Azure Cache for Redis' and armRegionName eq '{arm}' and priceType eq 'Consumption'"),
            # Global fallbacks (rows often omit region)
            ("serviceName eq 'Azure Cache for Redis' and priceType eq 'Consumption'"),
            # Be extra safe in case serviceName variants appear
            ("contains(serviceName,'Redis') and priceType eq 'Consumption'"),
        ]

        batches = [retail_fetch_items(f, currency) for f in filters]
        items: List[dict] = _dedup_merge(batches)

        # Keep positives and those that look like Redis instance hours
        items = [i for i in items if _d(i.get("retailPrice", 0)) > 0 and "redis" in _txt(i)]
        if not items:
            return _d(0), f"Redis {sku} (unpriced)"

        # Score and pick best row
        items.sort(key=lambda i: _score_redis_row(i, arm, sku_token, fam), reverse=True)
        row = items[0]
        unit = _d(row.get("retailPrice", 0))

    return unit * inst * hours, f"Redis {sku} x{inst} @ {unit}/hr × {hours}h"