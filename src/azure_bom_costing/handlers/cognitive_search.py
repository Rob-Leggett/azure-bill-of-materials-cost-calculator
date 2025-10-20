# =====================================================================================
# Azure Cognitive Search (Dedicated Search Units). Example component:
# {
#   "type": "cognitive_search",
#   "sku": "S1",
#   "replicas": 2,
#   "partitions": 1,
#   "hours_per_month": 730
# }
#
# Notes:
# • Models Azure Cognitive Search capacity-based billing using Search Units (SUs).
# • Each Search Unit = 1 partition × 1 replica.
# • Total SUs = replicas × partitions; billed hourly per SKU (e.g., S1, S2, S3, Basic).
#
# • Core parameters:
#     - `sku` → Search tier (Basic, S1, S2, S3, etc.)
#     - `replicas` → Number of replicas for query scaling & high availability
#     - `partitions` → Number of partitions for index storage/scaling
#     - `hours_per_month` → Total billed hours (default 730)
#
# • Pricing structure:
#     - serviceName eq 'Search'
#     - meterName contains '<SKU>' or 'Search Unit'
#     - unitOfMeasure = "1 Hour"
#
# • Enterprise lookup supported:
#     enterprise_lookup(ent_prices, "Search", f"{sku} Search Unit", region, "1 Hour")
# • Retail fallback queries the Azure Retail Prices API if enterprise sheet unavailable.
#
# • Calculation:
#     total_cost = rate_per_hour × replicas × partitions × hours
#
# • Example output:
#     Cog Search S1 SU:2 @ 0.50/hr × 730h = $730.00
#
# • Typical uses:
#     - Full-text indexing and search in web, enterprise, or e-commerce applications
#     - Scaling search workloads via replicas (query load) and partitions (index volume)
# • Excludes outbound egress or AI enrichment pipelines, which are billed separately.
# =====================================================================================
from decimal import Decimal
from typing import Dict, List

from ..helpers import _d, _arm_region, _dedup_merge, _pick, _text_fields
from ..pricing_sources import enterprise_lookup, retail_fetch_items, retail_pick
from ..types import Key

def _score_cogsearch_row(i: dict, arm_region: str, sku_l: str) -> int:
    """Score candidate rows: prefer 1 Hour, region, correct SKU, 'Search Unit' wording, positive price."""
    price = _d(i.get("retailPrice", 0))
    if price <= 0:
        return -999

    txt = _text_fields(i)
    uom = (i.get("unitOfMeasure") or "")
    s = 0
    if uom == "1 Hour": s += 6
    if (i.get("armRegionName") or "").lower() == arm_region: s += 4
    if "search" in txt: s += 3
    if "search unit" in txt or "su" in txt: s += 3
    # SKU match (S1/S2/S3/Basic etc.). Some rows omit it—so don't over-penalize.
    if sku_l and sku_l in txt:
        s += 3
    return s


def price_cognitive_search(component, region, currency, ent_prices: Dict[Key, Decimal]):
    sku = (component.get("sku") or "S1").upper()         # e.g., S1, S2, S3, BASIC
    replicas = _d(component.get("replicas", 1))
    parts = _d(component.get("partitions", 1))
    hours = _d(component.get("hours_per_month", 730))

    service, uom = "Search", "1 Hour"                    # enterprise sheet often uses "Search"
    key_sku = f"{sku} Search Unit"

    # Enterprise price first (per SU-hour)
    ent = enterprise_lookup(ent_prices, service, key_sku, region, uom)
    if ent is not None:
        unit = _d(ent)
    else:
        # Retail fallback
        arm = _arm_region(region)
        sku_l = sku.lower()

        # Try multiple service names; many catalogs use "Azure Cognitive Search".
        svc_names = ["Azure Cognitive Search", "Cognitive Search", "Search"]

        filters: List[str] = []
        for svc in svc_names:
            # Regioned, SKU-targeted rows first
            filters += [
                (f"serviceName eq '{svc}' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                 f"and (contains(skuName,'{sku}') or contains(productName,'{sku}') or contains(meterName,'{sku}'))"),
                # Regioned, generic Search Unit wording
                (f"serviceName eq '{svc}' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                 "and (contains(meterName,'Search Unit') or contains(productName,'Search Unit'))"),
            ]
        # Global fallbacks (some rows omit armRegionName)
        for svc in svc_names:
            filters += [
                (f"serviceName eq '{svc}' and priceType eq 'Consumption' "
                 f"and (contains(skuName,'{sku}') or contains(productName,'{sku}') or contains(meterName,'{sku}'))"),
                (f"serviceName eq '{svc}' and priceType eq 'Consumption' "
                 "and (contains(meterName,'Search Unit') or contains(productName,'Search Unit'))"),
            ]

        batches = [retail_fetch_items(f, currency) for f in filters]
        items = _dedup_merge(batches)

        # Prefer exact UOM, otherwise best-scored candidate
        row = retail_pick(items, "1 Hour")
        if not row:
            # Soft filter out obvious non-hourly or irrelevant rows
            cands = [i for i in items if _d(i.get("retailPrice", 0)) > 0]
            cands.sort(key=lambda i: _score_cogsearch_row(i, arm, sku_l), reverse=True)
            row = cands[0] if cands else None

        if not row:
            # Explicit message rather than silent $0
            return _d(0), f"Cog Search {sku} (Search Unit hourly price not found)"

        unit = _d(row.get("retailPrice", 0))

    su = replicas * parts
    total = unit * su * hours
    return total, f"Cog Search {sku} SU:{su} @ {unit}/hr × {hours}h"