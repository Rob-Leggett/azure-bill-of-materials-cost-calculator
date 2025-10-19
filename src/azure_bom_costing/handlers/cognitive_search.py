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
from typing import Dict

from ..helpers import _d, _arm_region, _dedup_merge, _pick
from ..pricing_sources import enterprise_lookup, retail_fetch_items
from ..types import Key


def price_cognitive_search(component, region, currency, ent_prices: Dict[Key, Decimal]):
    sku = (component.get("sku") or "S1").upper()
    replicas = _d(component.get("replicas", 1))
    parts = _d(component.get("partitions", 1))
    hours = _d(component.get("hours_per_month", 730))
    service, uom = "Search", "1 Hour"
    key_sku = f"{sku} Search Unit"
    ent = enterprise_lookup(ent_prices, service, key_sku, region, uom)
    if ent is None:
        arm = _arm_region(region)
        filters = [
            (f"serviceName eq 'Search' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
             f"and (contains(skuName,'{sku}') or contains(meterName,'{sku}'))"),
            ("serviceName eq 'Search' and priceType eq 'Consumption' and contains(meterName,'Search Unit')")
        ]
        row = _pick(_dedup_merge([retail_fetch_items(f, currency) for f in filters]), uom)
        unit = _d(row.get("retailPrice", 0)) if row else _d(0)
    else:
        unit = ent
    su = replicas * parts
    return unit * su * hours, f"Cog Search {sku} SU:{su} @ {unit}/hr × {hours}h"