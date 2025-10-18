from decimal import Decimal
from typing import Dict, Optional, List

from .common import _arm_region
from ..pricing_sources import d, retail_fetch_items, enterprise_lookup
from ..types import Key

# ---------- Virtual Machines ----------
def _pick_vm_item(items: List[dict], os_filter: str, prefer_uom: str = "1 Hour") -> Optional[dict]:
    """Prefer 1 Hour meters; try to match OS label across meterName, productName, skuName; fallback gracefully."""
    if not items:
        return None

    os_lower = os_filter.lower()

    def has_os(i: dict) -> bool:
        return any(os_lower in (i.get(k, "") or "").lower()
                   for k in ("meterName", "productName", "skuName"))

    # 1) 1 Hour + OS
    for i in items:
        if i.get("unitOfMeasure") == prefer_uom and has_os(i) and d(i.get("retailPrice", 0)) > 0:
            return i
    # 2) Any UOM + OS
    for i in items:
        if has_os(i) and d(i.get("retailPrice", 0)) > 0:
            return i
    # 3) 1 Hour, any OS
    for i in items:
        if i.get("unitOfMeasure") == prefer_uom and d(i.get("retailPrice", 0)) > 0:
            return i
    # 4) First positive price
    for i in items:
        if d(i.get("retailPrice", 0)) > 0:
            return i
    return items[0] if items else None

def _fallback_vm_items(sku: str, arm_region: str, currency: str) -> List[dict]:
    """Try broader VM queries if the strict SKU filter yields nothing."""
    filt = (
        "serviceName eq 'Virtual Machines' "
        f"and armRegionName eq '{arm_region}' "
        "and priceType eq 'Consumption'"
    )
    items = retail_fetch_items(filt, currency)
    if not items:
        return []
    sku_l = sku.lower()
    narrowed = [
        i for i in items
        if sku_l in (i.get("armSkuName","") or "").lower()
           or sku_l in (i.get("skuName","") or "").lower()
           or sku_l in (i.get("productName","") or "").lower()
           or sku_l in (i.get("meterName","") or "").lower()
    ]
    return narrowed or items

def price_vm(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = "Virtual Machines"
    sku = component["armSku"]  # e.g. "Standard_D4s_v5"
    os_filter = "Linux" if component.get("os", "").lower().startswith("lin") else "Windows"
    uom = "1 Hour"

    ent = enterprise_lookup(ent_prices, service, sku, region, uom)
    if ent is None:
        arm_region = _arm_region(region)
        filt = (
            "serviceName eq 'Virtual Machines' "
            f"and armSkuName eq '{sku}' "
            f"and armRegionName eq '{arm_region}' "
            "and priceType eq 'Consumption'"
        )
        items = retail_fetch_items(filt, currency)
        if not items:
            items = _fallback_vm_items(sku, arm_region, currency)
        row = _pick_vm_item(items, os_filter, uom)
        if not row:
            raise RuntimeError(f"No retail price for VM {sku} (region={arm_region})")
        unit = d(row.get("retailPrice", 0))
    else:
        unit = ent

    hours = d(component.get("hours_per_month", 730))
    count = d(component.get("count", 1))
    return unit * hours * count, f"VM {sku} x{count} @ {unit}/hr"