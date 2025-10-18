from decimal import Decimal
from typing import List, Optional, Dict

from .common import _arm_region
from ..pricing_sources import d, enterprise_lookup, retail_fetch_items
from ..types import Key

# ---------- App Service ----------
def _appsvc_tier_hint(sku: str) -> Optional[str]:
    """Rough productName tier hint from SKU (for broader fallbacks)."""
    s = sku.lower()
    if "v3" in s:
        return "Premium v3"
    if s.startswith("p"):
        return "Premium"
    if s.startswith("s"):
        return "Standard"
    if s.startswith("b"):
        return "Basic"
    return None

def _pick_app_service(items: List[dict], arm_region: str, prefer_uom: str = "1 Hour") -> Optional[dict]:
    """Prefer items with matching region and 1 Hour UOM; then relax."""
    if not items:
        return None

    # 1) Region + 1 Hour
    for i in items:
        if i.get("armRegionName") == arm_region and i.get("unitOfMeasure") == prefer_uom and d(i.get("retailPrice", 0)) > 0:
            return i
    # 2) Region any UOM
    for i in items:
        if i.get("armRegionName") == arm_region and d(i.get("retailPrice", 0)) > 0:
            return i
    # 3) Any region + 1 Hour
    for i in items:
        if i.get("unitOfMeasure") == prefer_uom and d(i.get("retailPrice", 0)) > 0:
            return i
    # 4) Any positive
    for i in items:
        if d(i.get("retailPrice", 0)) > 0:
            return i
    return items[0]

def price_app_service(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = "App Service"
    sku = component["sku"]              # e.g. "P1v3"
    uom = "1 Hour"

    ent = enterprise_lookup(ent_prices, service, sku, region, uom)
    if ent is None:
        arm_region = _arm_region(region)

        # Build a cascade of increasingly broad filters. We'll dedupe/merge results.
        filters: List[str] = [
            # Strict matches first
            ("serviceName eq 'App Service' "
             f"and skuName eq '{sku}' "
             f"and armRegionName eq '{arm_region}' "
             "and priceType eq 'Consumption'"),
            ("serviceName eq 'App Service' "
             f"and contains(skuName,'{sku}') "
             f"and armRegionName eq '{arm_region}' "
             "and priceType eq 'Consumption'"),

            # Same but without region (some rows omit armRegionName)
            ("serviceName eq 'App Service' "
             f"and skuName eq '{sku}' "
             "and priceType eq 'Consumption'"),
            ("serviceName eq 'App Service' "
             f"and contains(skuName,'{sku}') "
             "and priceType eq 'Consumption'"),

            # Match by productName carrying the tier words
            ("serviceName eq 'App Service' "
             "and contains(productName,'App Service') "
             f"and contains(productName,'{sku}') "
             "and priceType eq 'Consumption'"),
        ]

        hint = _appsvc_tier_hint(sku)  # e.g. "Premium v3" for P1v3
        if hint:
            filters += [
                ("serviceName eq 'App Service' "
                 f"and contains(productName,'{hint}') "
                 "and priceType eq 'Consumption'"),
                ("contains(productName,'App Service') "
                 f"and contains(productName,'{hint}') "
                 "and priceType eq 'Consumption'"),
            ]

        filters += [
            ("contains(productName,'App Service') "
             f"and contains(skuName,'{sku}') "
             "and priceType eq 'Consumption'"),
            ("serviceFamily eq 'Compute' "
             "and contains(productName,'App Service') "
             "and priceType eq 'Consumption'"),
        ]

        # Fetch & dedupe
        items: List[dict] = []
        seen = set()
        for f in filters:
            try:
                chunk = retail_fetch_items(f, currency)
                for it in chunk:
                    key = it.get("meterId") or (it.get("productId"), it.get("skuId"), it.get("meterName"))
                    if key not in seen:
                        seen.add(key)
                        items.append(it)
            except Exception:
                pass

        row = _pick_app_service(items, arm_region, uom)
        if not row:
            raise RuntimeError(f"No retail price for App Service {sku} (region={arm_region})")
        unit = d(row.get("retailPrice", 0))
    else:
        unit = ent

    hours = d(component.get("hours_per_month", 730))
    inst = d(component.get("instances", 1))
    return unit * hours * inst, f"AppService {sku} x{inst} @ {unit}/hr"