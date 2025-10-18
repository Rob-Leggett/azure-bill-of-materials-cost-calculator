# =========================================================
# Azure Container Apps (consumption): vCPU-sec, Mem-GB-sec, Requests per 1M
# component:
#   { "type":"container_apps", "vcpu_seconds": 3_000_000, "memory_gb_seconds": 6_000_000, "requests_1m": 5 }
# =========================================================
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