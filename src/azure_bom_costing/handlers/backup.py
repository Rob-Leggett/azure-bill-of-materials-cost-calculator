# =========================================================
# Azure Backup (simplified to Backup Storage + optional protected instances)
# component:
#   { "type":"backup", "backup_storage_tb": 2, "redundancy":"LRS|GRS", "instances_small": 5, "instances_medium": 2 }
# =========================================================
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