# =========================================================
# Redis Cache
# component: { "type":"redis", "sku":"C1|C2|P1|P2|E10", "instances":1, "hours_per_month":730 }
# =========================================================
from decimal import Decimal
from typing import Dict

from ..helpers import _d, _arm_region, _pick, _dedup_merge
from ..pricing_sources import enterprise_lookup, retail_fetch_items
from ..types import Key


def price_redis(component, region, currency, ent_prices: Dict[Key, Decimal]):
    sku = component.get("sku", "C1").upper()
    inst = _d(component.get("instances", 1))
    hours = _d(component.get("hours_per_month", 730))
    service, uom = "Azure Cache for Redis", "1 Hour"

    ent = enterprise_lookup(ent_prices, service, sku, region, uom)
    if ent is None:
        arm = _arm_region(region)
        filters = [
            (f"serviceName eq 'Azure Cache for Redis' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
             f"and (contains(skuName,'{sku}') or contains(meterName,'{sku}'))"),
            ("serviceName eq 'Azure Cache for Redis' and priceType eq 'Consumption'")
        ]
        row = _pick(_dedup_merge([retail_fetch_items(f, currency) for f in filters]), uom)
        unit = _d(row.get("retailPrice", 0)) if row else _d(0)
    else:
        unit = ent

    return unit * inst * hours, f"Redis {sku} x{inst} @ {unit}/hr × {hours}h"