# =====================================================================================
# Azure App Service (Dedicated Plan). Example component:
# {
#   "type": "app_service",
#   "sku": "P1v3",
#   "instances": 2,
#   "hours_per_month": 730,
#   "os": "linux"          # optional: "linux" | "windows"
# }
#
# Notes:
# • Models compute cost for dedicated Azure App Service Plans (Basic, Standard, Premium v2/v3).
# • Each SKU (e.g. P1v3, S1, B1) represents a specific VM tier and size class.
# • Pricing is per instance per hour.
#
# • Core parameters:
#     - `sku` → SKU name (e.g., "B1", "S1", "P1v3", etc.)
#     - `instances` → Number of App Service instances
#     - `hours_per_month` → Total runtime hours (default 730)
#
# • Pricing structure:
#     - serviceName eq 'App Service'
#     - skuName or productName contains the SKU (e.g. 'P1v3', 'S1', 'Premium v3')
#     - unitOfMeasure = "1 Hour"
# • Uses a fallback sequence:
#     1. Exact SKU + region
#     2. SKU without region (some catalog rows omit armRegionName)
#     3. Product name or tier hint (e.g. "Premium v3", "Standard", "Basic")
#     4. General "App Service" rows in Compute service family
#
# • Enterprise lookup supported:
#     enterprise_lookup(ent_prices, "App Service", sku, region, "1 Hour")
# • Retail fallback retrieves from Azure Retail Prices API with multiple filters for resiliency.
#
# • Calculation:
#     total_cost = rate_per_hour × instances × hours_per_month
#
# • Example output:
#     AppService P1v3 x2 @ 0.25/hr × 730h = $365.00
#
# • Typical uses:
#     - Hosting web applications, APIs, or background jobs on App Service Plans
#     - Supports Windows and Linux plans (same SKU pattern)
# • Excludes Consumption-based Azure Functions or Elastic Premium plans (handled separately).
# =====================================================================================
from decimal import Decimal
from typing import List, Optional, Dict
from ..helpers import _d, _arm_region, _dedup_merge
from ..pricing_sources import enterprise_lookup, retail_fetch_items
from ..types import Key

# ---------- App Service ----------
_BAD_TOKENS = {
    # Not plan instance-hour meters
    "stamp", "stamp fee", "environment base", "app service environment", "ase", "ase v2", "ase v3",
    "isolated", "isolated v2",
    # Not dedicated app service plan
    "functions", "function app",
    # Non-dedicated tiers
    "free", "shared",
}

_SERVICE_VARIANTS = [
    "App Service",
    "App Service - Linux",
    "App Service - Windows",
    "Azure App Service",  # seen in some catalogs
]

def _appsvc_tier_hint(sku: str) -> Optional[str]:
    s = (sku or "").lower()
    if "v3" in s:
        return "Premium v3"
    if s.startswith("p"):
        return "Premium"
    if s.startswith("s"):
        return "Standard"
    if s.startswith("b"):
        return "Basic"
    return None

def _is_bad_row(i: dict) -> bool:
    txt = " ".join([
        i.get("serviceName",""),
        i.get("productName",""),
        i.get("skuName",""),
        i.get("meterName",""),
    ]).lower()
    return any(tok in txt for tok in _BAD_TOKENS)

def _mentions_sku(i: dict, sku: str) -> bool:
    sku_l = (sku or "").lower()
    # Allow both "P1v3" and "P1 v3" forms
    spaced = sku_l.replace("v", " v")
    text = " ".join([
        i.get("skuName",""), i.get("meterName",""), i.get("productName","")
    ]).lower()
    return (
            (i.get("skuName","").strip().lower() == sku_l)
            or (sku_l in text)
            or (spaced in text)
    )

def _ok_plan_row(i: dict, sku: str) -> bool:
    if _d(i.get("retailPrice", 0)) <= 0:
        return False
    if i.get("unitOfMeasure") != "1 Hour":
        return False
    if _is_bad_row(i):
        return False
    # Must be clearly App Service family (serviceName OR productName)
    fam = (i.get("serviceName","") + " " + i.get("productName","")).lower()
    if "app service" not in fam:
        return False
    # Must mention SKU somewhere
    if not _mentions_sku(i, sku):
        return False
    return True

def _pick_app_service(items: List[dict], sku: str, arm_region: str) -> Optional[dict]:
    cands = [i for i in items if _ok_plan_row(i, sku)]
    if not cands:
        return None

    # Prefer exact region, then lowest price
    def key(i: dict):
        region_match = 1 if (i.get("armRegionName") or "") == arm_region else 0
        price = _d(i.get("retailPrice", 0))
        return (-region_match, price)

    cands.sort(key=key)
    # sanity: if top is still suspicious (> $1.50/hr), choose the lowest *exact skuName* match
    top = cands[0]
    if _d(top.get("retailPrice", 0)) > _d("1.50"):
        exacts = [i for i in cands if (i.get("skuName","") or "").strip() == sku]
        if exacts:
            exacts.sort(key=lambda j: _d(j.get("retailPrice", 0)))
            return exacts[0]
    return top

def price_app_service(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = "App Service"
    sku = component["sku"]              # e.g. "P1v3"
    uom = "1 Hour"
    os_hint = (component.get("os") or "").strip().lower()  # "linux" | "windows" | ""

    # 1) Enterprise first
    ent = enterprise_lookup(ent_prices, service, sku, region, uom)
    if ent is not None:
        unit = ent
    else:
        arm_region = _arm_region(region)
        tier_hint = _appsvc_tier_hint(sku)

        filters: List[str] = []

        # Strict by serviceName variants + skuName (regioned and global)
        for svc in _SERVICE_VARIANTS:
            filters += [
                (f"serviceName eq '{svc}' and skuName eq '{sku}' "
                 f"and armRegionName eq '{arm_region}' and priceType eq 'Consumption'"),
                (f"serviceName eq '{svc}' and skuName eq '{sku}' and priceType eq 'Consumption'"),
                (f"serviceName eq '{svc}' and contains(skuName,'{sku}') "
                 f"and armRegionName eq '{arm_region}' and priceType eq 'Consumption'"),
                (f"serviceName eq '{svc}' and contains(skuName,'{sku}') and priceType eq 'Consumption'"),
                (f"serviceName eq '{svc}' and contains(productName,'App Service') "
                 f"and contains(productName,'{sku}') and priceType eq 'Consumption'"),
                (f"serviceName eq '{svc}' and contains(meterName,'{sku}') and priceType eq 'Consumption'"),
            ]

        # Tier hint (Premium v3 / Standard / Basic) helps when SKU not duplicated into skuName
        if tier_hint:
            for svc in _SERVICE_VARIANTS:
                filters += [
                    (f"serviceName eq '{svc}' and contains(productName,'{tier_hint}') and priceType eq 'Consumption'"),
                    (f"contains(productName,'App Service') and contains(productName,'{tier_hint}') "
                     "and priceType eq 'Consumption'"),
                ]

        # Very broad fallbacks
        filters += [
            ("contains(productName,'App Service') and priceType eq 'Consumption'"),
            ("serviceFamily eq 'Compute' and contains(productName,'App Service') and priceType eq 'Consumption'"),
        ]

        batches = [retail_fetch_items(f, currency) for f in filters]
        items: List[dict] = _dedup_merge(batches)

        # Optional OS narrowing (keep neutral rows too)
        if os_hint in ("linux", "windows"):
            def os_ok(i: dict) -> bool:
                txt = " ".join([i.get("productName",""), i.get("skuName",""), i.get("meterName","")]).lower()
                has_win = "windows" in txt
                has_lin = "linux" in txt
                if os_hint == "linux":
                    return has_lin or (not has_win and not has_lin)
                else:
                    return has_win or (not has_win and not has_lin)
            items = [i for i in items if os_ok(i)]

        row = _pick_app_service(items, sku, arm_region)

        # Last-chance: choose the cheapest positive “1 Hour” row that mentions the SKU and is not bad
        if not row:
            fallbacks = [
                i for i in items
                if (i.get("unitOfMeasure") == "1 Hour")
                   and _mentions_sku(i, sku)
                   and not _is_bad_row(i)
                   and _d(i.get("retailPrice", 0)) > 0
            ]
            fallbacks.sort(key=lambda i: _d(i.get("retailPrice", 0)))
            row = fallbacks[0] if fallbacks else None

        if not row:
            # Don’t crash the whole run; report unpriced
            hours = _d(component.get("hours_per_month", 730))
            inst = _d(component.get("instances", 1))
            return _d(0), f"AppService {sku} x{inst} (unpriced — no suitable retail row)"

        unit = _d(row.get("retailPrice", 0))

        # Guardrail against stray ASE/stamp: clamp to the min acceptable exact-SKU price if too high
        if unit > _d("1.50"):
            exacts = [
                i for i in items
                if (i.get("unitOfMeasure") == "1 Hour")
                   and (i.get("skuName","") or "").strip() == sku
                   and not _is_bad_row(i)
                   and _d(i.get("retailPrice", 0)) > 0
            ]
            exacts.sort(key=lambda j: _d(j.get("retailPrice", 0)))
            if exacts:
                unit2 = _d(exacts[0].get("retailPrice", 0))
                if unit2 > 0:
                    unit = unit2

    hours = _d(component.get("hours_per_month", 730))
    inst = _d(component.get("instances", 1))
    return unit * hours * inst, f"AppService {sku} x{inst} @ {unit}/hr"