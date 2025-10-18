# =========================================================
# Azure Cognitive Search
# component: { "type":"cognitive_search", "sku":"S1|S2|S3|Basic", "replicas": 2, "partitions": 1, "hours_per_month":730 }
# =========================================================
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