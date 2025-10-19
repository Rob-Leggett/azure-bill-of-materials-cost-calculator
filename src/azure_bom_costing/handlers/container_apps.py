# =====================================================================================
# Azure Container Apps (consumption-based pricing). Example component:
# {
#   "type": "container_apps",
#   "vcpu_seconds": 3_000_000,
#   "memory_gb_seconds": 6_000_000,
#   "requests_1m": 5
# }
#
# Notes:
# • Models serverless Azure Container Apps cost structure (Consumption plan).
# • Charges are based on three dimensions:
#     - vCPU Duration (per million seconds)
#     - Memory Duration (per million GB-seconds)
#     - HTTP Requests (per 1 million requests)
#
# • Core parameters:
#     - `vcpu_seconds` → Total vCPU time in seconds
#     - `memory_gb_seconds` → Total memory usage in GB-seconds
#     - `requests_1m` → Number of HTTP requests (in millions)
#
# • Pricing structure (Retail API filters):
#     - serviceName eq 'Container Apps'
#     - meterName contains 'vCPU Duration'  →  unitOfMeasure: "1,000,000 Seconds"
#     - meterName contains 'Memory Duration' → unitOfMeasure: "1,000,000 GB Seconds"
#     - meterName contains 'Requests'       → unitOfMeasure: "1,000,000"
#
# • Enterprise lookup supported:
#     enterprise_lookup(ent_prices, "Container Apps", "vCPU Duration", region, "1,000,000 Seconds")
#     enterprise_lookup(ent_prices, "Container Apps", "Memory Duration", region, "1,000,000 GB Seconds")
#     enterprise_lookup(ent_prices, "Container Apps", "Requests", region, "1,000,000")
#
# • Calculation:
#     total_cost = (vcpu_seconds × rate_per_1M_sec / 1M)
#                + (memory_gb_seconds × rate_per_1M_GBsec / 1M)
#                + (requests_1m × rate_per_1M)
#
# • Example output:
#     Container Apps (vCPU:3M s, Mem:6M GB-s, Req:5M) = $15.20
#
# • Typical uses:
#     - Serverless APIs or background workloads on Container Apps (Consumption plan)
#     - Stateless, auto-scaling microservices without dedicated infrastructure
# • Premium / Dedicated plans (with vCPU-hrs) should be modeled separately under VM costs.
# =====================================================================================
from decimal import Decimal
from typing import Dict

from ..helpers import _d, _pick, _arm_region
from ..pricing_sources import retail_pick, retail_fetch_items, enterprise_lookup
from ..types import Key


def price_container_apps(component, region, currency, ent_prices: Dict[Key, Decimal]):
    vcpu_s  = _d(component.get("vcpu_seconds", 0))
    mem_gbs = _d(component.get("memory_gb_seconds", 0))
    req_1m  = _d(component.get("requests_1m", 0))
    arm = _arm_region(region)

    total = _d(0)

    # vCPU Duration
    if vcpu_s > 0:
        service, sku, uom = "Container Apps", "vCPU Duration", "1,000,000 Seconds"
        ent = enterprise_lookup(ent_prices, service, sku, region, uom)
        if ent is None:
            flt = (f"serviceName eq 'Container Apps' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                   "and contains(meterName,'vCPU Duration')")
            row = retail_pick(retail_fetch_items(flt, currency), uom) or _pick(retail_fetch_items(flt, currency))
            unit_per_msec = _d(row.get("retailPrice", 0)) if row else _d(0)
        else:
            unit_per_msec = ent
        total += unit_per_msec * (vcpu_s / _d(1_000_000))

    # Memory Duration
    if mem_gbs > 0:
        service, sku, uom = "Container Apps", "Memory Duration", "1,000,000 GB Seconds"
        ent = enterprise_lookup(ent_prices, service, sku, region, uom)
        if ent is None:
            flt = (f"serviceName eq 'Container Apps' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                   "and contains(meterName,'Memory Duration')")
            row = retail_pick(retail_fetch_items(flt, currency), uom) or _pick(retail_fetch_items(flt, currency))
            unit_per_mgbsec = _d(row.get("retailPrice", 0)) if row else _d(0)
        else:
            unit_per_mgbsec = ent
        total += unit_per_mgbsec * (mem_gbs / _d(1_000_000))

    # Requests per 1M
    if req_1m > 0:
        service, sku, uom = "Container Apps", "Requests", "1,000,000"
        ent = enterprise_lookup(ent_prices, service, sku, region, uom)
        if ent is None:
            flt = ("serviceName eq 'Container Apps' and priceType eq 'Consumption' "
                   "and (contains(meterName,'Requests') or contains(productName,'Requests'))")
            row = retail_pick(retail_fetch_items(flt, currency), uom) or _pick(retail_fetch_items(flt, currency))
            unit_per_m = _d(row.get("retailPrice", 0)) if row else _d(0)
        else:
            unit_per_m = ent
        total += unit_per_m * req_1m

    return total, "Container Apps (vCPU/Mem/Requests)"