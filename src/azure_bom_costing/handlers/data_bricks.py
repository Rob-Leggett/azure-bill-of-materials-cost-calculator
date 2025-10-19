# =====================================================================================
# Azure Databricks (DBU-based pricing model). Example component:
# {
#   "type": "databricks",
#   "tier": "Premium",
#   "dbu_hours": 500
# }
#
# Notes:
# • Models Databricks usage based on *Databricks Units (DBUs)* — the core consumption metric.
# • VM/compute costs (e.g., node VMs, spot instances) should be modeled separately under "vm".
#
# • Core parameters:
#     - `tier` → Databricks plan tier ("Standard", "Premium", "Enterprise")
#     - `dbu_hours` → Total Databricks Unit hours consumed in the billing period
#
# • Pricing structure:
#     - serviceName eq 'Azure Databricks'
#     - meterName contains 'DBU'
#     - unitOfMeasure = "1 Hour"
# • Tiers may appear under SKU/meterName (e.g. "Premium DBU", "Enterprise DBU")
#
# • Enterprise lookup supported:
#     enterprise_lookup(ent_prices, "Azure Databricks", f"{tier} DBU", region, "1 Hour")
# • Retail fallback via Azure Retail Prices API if enterprise sheet unavailable.
#
# • Calculation:
#     total_cost = DBU_hours × unit_rate_per_hour
#
# • Example output:
#     Databricks Premium @ 0.45/DBU-hr × 500h = $225.00
#
# • Typical uses:
#     - Databricks clusters for data engineering or machine learning workloads.
#     - Interactive or job compute tied to workspace DBU consumption.
# • Excludes VM, storage, or network costs — these should be modeled separately.
# =====================================================================================
from decimal import Decimal
from typing import Dict, List
from ..helpers import _d, _arm_region, _pick
from ..pricing_sources import enterprise_lookup, retail_fetch_items
from ..types import Key

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