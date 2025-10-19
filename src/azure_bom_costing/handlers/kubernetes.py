# =====================================================================================
# Azure Kubernetes Service (AKS) – Control Plane / Uptime SLA. Example component:
# {
#   "type": "aks_cluster",
#   "uptime_sla": true,
#   "hours_per_month": 730
# }
#
# Notes:
# • Models AKS control plane cost for clusters with the Uptime SLA enabled.
# • Node compute and storage costs should be modeled separately using the "vm" component.
# • When `uptime_sla` is false, AKS control plane is free (no hourly charge).
#
# • Core parameters:
#     - `uptime_sla` → Boolean flag for whether Uptime SLA is enabled
#     - `hours_per_month` → Number of hours billed (default 730)
#
# • Pricing structure:
#     - serviceName eq 'Azure Kubernetes Service' or 'Kubernetes Service (AKS)'
#     - meterName or skuName contains 'Uptime SLA'
#     - unitOfMeasure = "1 Hour"
#
# • Enterprise lookup supported:
#     enterprise_lookup(ent_prices, "Azure Kubernetes Service", "Uptime SLA", region, "1 Hour")
# • Retail fallback queries Azure Retail Prices API with:
#     serviceName = 'Azure Kubernetes Service' or 'Kubernetes Service (AKS)'
#     priceType = 'Consumption'
#     meterName/skuName includes 'Uptime'
#
# • Calculation:
#     total_cost = hours_per_month × rate_per_hour
#
# • Example output:
#     AKS Uptime SLA @ 0.10/hr × 730h = $73.00
#
# • Typical uses:
#     - Adds reliability guarantees for AKS control plane availability (99.95%)
#     - Applied to production AKS clusters where uptime SLA is enabled
#     - Free for clusters without Uptime SLA
#
# • Excludes:
#     - Worker node VM and storage costs (handled via separate “vm” and “storage” components)
# =====================================================================================
from decimal import Decimal
from typing import List, Dict

from ..helpers import _d, _arm_region, _pick
from ..pricing_sources import retail_fetch_items, enterprise_lookup
from ..types import Key


def price_aks_cluster(component, region, currency, ent_prices: Dict[Key, Decimal]):
    hours = _d(component.get("hours_per_month", 730))
    if not component.get("uptime_sla", True):
        return _d(0), "AKS control plane (no Uptime SLA)"

    service, sku, uom = "Azure Kubernetes Service", "Uptime SLA", "1 Hour"
    ent = enterprise_lookup(ent_prices, service, sku, region, uom)
    if ent is not None:
        unit = ent
    else:
        arm = _arm_region(region)
        # Some catalogs use serviceName "Kubernetes Service (AKS)"
        filters = [
            (f"serviceName eq 'Azure Kubernetes Service' and armRegionName eq '{arm}' "
             "and priceType eq 'Consumption' and (contains(meterName,'Uptime') or contains(skuName,'Uptime'))"),
            ("serviceName eq 'Azure Kubernetes Service' and priceType eq 'Consumption' "
             "and (contains(meterName,'Uptime') or contains(skuName,'Uptime'))"),
            (f"serviceName eq 'Kubernetes Service (AKS)' and armRegionName eq '{arm}' and priceType eq 'Consumption'"),
        ]
        items: List[dict] = []
        for f in filters:
            items += retail_fetch_items(f, currency)
        row = _pick(items, uom)
        if not row:
            # Don’t block the run if the catalog is odd
            return _d(0), "AKS Uptime SLA (unpriced)"
        unit = _d(row.get("retailPrice", 0))

    return unit * hours, f"AKS Uptime SLA @ {unit}/hr × {hours}h"