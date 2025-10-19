# =====================================================================================
# Azure Backup (simplified to Backup Storage + optional Protected Instances). Example component:
# {
#   "type": "backup",
#   "backup_storage_tb": 2,
#   "redundancy": "LRS",
#   "instances_small": 5,
#   "instances_medium": 2
# }
#
# Notes:
# • Models Azure Backup costs based on:
#     1. Backup Storage (LRS or GRS, per GB-month)
#     2. Protected Instances (per-instance monthly fee by size category)
#
# • Core parameters:
#     - `backup_storage_tb` → Total protected backup storage in TB
#     - `redundancy` → "LRS" (locally redundant) or "GRS" (geo-redundant)
#     - `instances_small` → Count of small protected instances (≤50 GB)
#     - `instances_medium` → Count of medium instances (50–500 GB)
#     - `instances_large` → Count of large instances (>500 GB)
#
# • Pricing structure:
#     - serviceName eq 'Azure Backup'
#     - meterName contains 'Backup Storage' (unitOfMeasure: "1 GB/Month")
#     - meterName contains 'Protected Instance' (unitOfMeasure: "1/Month")
#
# • Enterprise lookup supported:
#     enterprise_lookup(ent_prices, "Azure Backup", f"Backup Storage {redundancy}", region, "1 GB/Month")
#     enterprise_lookup(ent_prices, "Azure Backup", "Protected Instance Small|Medium|Large", region, "1/Month")
# • Retail fallback queries Azure Retail Prices API when enterprise sheet unavailable.
#
# • Calculation:
#     total_cost = (backup_storage_tb × 1024 × rate_per_GB_month)
#                + Σ (instances_small|medium|large × rate_per_instance_month)
#
# • Example output:
#     Azure Backup (storage:2TB LRS + 5 small + 2 medium) = $47.90
#
# • Typical uses:
#     - VM, SQL, or File Share backups through Recovery Services vaults
#     - DR strategy modeling where backup retention and redundancy type matter
# • Does not include Azure Site Recovery (ASR); model separately if used.
# =====================================================================================
from decimal import Decimal
from typing import Dict

from ..helpers import _d, _pick, _arm_region
from ..pricing_sources import enterprise_lookup, retail_fetch_items, retail_pick
from ..types import Key


def price_backup(component, region, currency, ent_prices: Dict[Key, Decimal]):
    arm = _arm_region(region)
    total = _d(0)

    # Storage (per GB-month)
    tb = _d(component.get("backup_storage_tb", 0))
    if tb > 0:
        gb = tb * _d(1024)
        redundancy = (component.get("redundancy") or "LRS").upper()
        service, uom = "Azure Backup", "1 GB/Month"
        sku = f"Backup Storage {redundancy}"
        ent = enterprise_lookup(ent_prices, service, sku, region, uom)
        if ent is not None:
            unit = ent
        else:
            flt = (f"serviceName eq 'Azure Backup' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                   "and (contains(meterName,'Backup Storage') or contains(productName,'Backup Storage'))")
            row = retail_pick(retail_fetch_items(flt, currency), uom) or _pick(retail_fetch_items(flt, currency))
            unit = _d(row.get("retailPrice", 0)) if row else _d(0)
        total += unit * gb

    # Protected Instances (very rough buckets)
    # small (<=50GB), medium (50-500GB), large (>500GB)
    def _pi(bucket_name: str, count_key: str):
        cnt = _d(component.get(count_key, 0))
        if cnt <= 0:
            return _d(0)
        service, uom = "Azure Backup", "1/Month"
        sku = f"Protected Instance {bucket_name}"
        ent = enterprise_lookup(ent_prices, service, sku, region, uom)
        if ent is not None:
            unit = ent
        else:
            flt = ("serviceName eq 'Azure Backup' and priceType eq 'Consumption' "
                   f"and contains(meterName,'Protected Instance') and contains(meterName,'{bucket_name}')")
            row = retail_pick(retail_fetch_items(flt, currency), uom) or _pick(retail_fetch_items(flt, currency))
            unit = _d(row.get("retailPrice", 0)) if row else _d(0)
        return unit * cnt

    total += _pi("Small", "instances_small")
    total += _pi("Medium", "instances_medium")
    total += _pi("Large", "instances_large")

    return total, "Azure Backup (storage + protected instances)"