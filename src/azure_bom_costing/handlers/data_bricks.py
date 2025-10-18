from decimal import Decimal
from typing import Dict, List

from ..helpers import _d, _arm_region, _pick
from ..pricing_sources import enterprise_lookup, retail_fetch_items
from ..types import Key

# =====================================================================================
# Databricks (DBU only; VM/spot costs model separately as VMs)
# component: { "type":"databricks", "tier":"Premium", "dbu_hours": 500 }
# =====================================================================================
def price_databricks(component, region, currency, ent_prices: Dict[Key, Decimal]):
    tier = component.get("tier", "Premium")  # Standard | Premium | Enterprise
    dbu_hours = _d(component.get("dbu_hours", 0))
    if dbu_hours <= 0:
        return _d(0), "Databricks (0 DBU hours)"

    service, uom = "Azure Databricks", "1 Hour"
    sku = f"{tier} DBU"

    ent = enterprise_lookup(ent_prices, service, sku, region, uom)
    if ent is not None:
        unit = ent
    else:
        arm = _arm_region(region)
        filters = [
            (f"serviceName eq 'Azure Databricks' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
             f"and (contains(meterName,'DBU') or contains(skuName,'{tier}'))"),
            ("serviceName eq 'Azure Databricks' and priceType eq 'Consumption' and contains(meterName,'DBU')"),
        ]
        items: List[dict] = []
        for f in filters:
            items += retail_fetch_items(f, currency)
        row = _pick(items, uom)
        if not row:
            return _d(0), "Databricks DBU (unpriced)"
        unit = _d(row.get("retailPrice", 0))

    return unit * dbu_hours, f"Databricks {tier} @ {unit}/DBU-hr × {dbu_hours}h"