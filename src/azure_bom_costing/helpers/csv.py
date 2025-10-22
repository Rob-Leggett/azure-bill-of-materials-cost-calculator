from typing import Dict, Optional, Any, Iterable, List

from .math import decimal

# ------------------------------------------------------------
# Allowed headings (the CSV schema we will strictly adhere to)
# ------------------------------------------------------------
ALLOWED_HEADINGS = (
    "serviceName","productName","skuName","meterName","unitOfMeasure",
    "retailPrice","currencyCode","armRegionName","priceType","effectiveStartDate",
    "meterId","skuId","productId","effectiveEndDate","unitPrice",
    "serviceId","location","savingsPlan","isPrimaryMeterRegion","serviceFamily",
    "type","reservationTerm","armSkuName","tierMinimumUnits"
)

# Provide stable, minimal defaults so downstream code/CSV always sees these keys.
# Note: we intentionally do *not* invent values; we only set safe blanks where Azure might omit a field.
_DEFAULTS: Dict[str, Optional[str]] = {
    "serviceName": None,
    "productName": None,
    "skuName": None,
    "meterName": None,
    "unitOfMeasure": None,
    "retailPrice": None,
    "currencyCode": None,
    "armRegionName": None,
    "priceType": None,
    "effectiveStartDate": None,
    "meterId": None,
    "skuId": None,
    "productId": None,
    "effectiveEndDate": None,
    "unitPrice": None,
    "serviceId": None,
    "location": None,
    "savingsPlan": None,
    "isPrimaryMeterRegion": None,
    "serviceFamily": None,
    "type": None,
    "reservationTerm": None,
    "armSkuName": None,
    "tierMinimumUnits": None,
}

# =====================================================================================
# "Australia East" -> "australiaeast"
# =====================================================================================
def arm_region(region_str: str) -> str:
    return region_str.strip().lower().replace(" ", "")

def clean_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [_clean_row_to_allowed(r) for r in rows]

def dedup_merge(lists: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Merge lists of canonical retail rows, de-duping by (meterId or (serviceName, skuName, meterName, unitOfMeasure, armRegionName))."""
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for lst in lists:
        for r in lst or []:
            key = (
                    r.get("meterId")
                    or (
                        r.get("serviceName"),
                        r.get("skuName"),
                        r.get("meterName"),
                        r.get("unitOfMeasure"),
                        r.get("armRegionName"),
                    )
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
    return out

def pick_first(d: Dict[str, Any], *keys: str) -> Optional[Any]:
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None

def pick(items: List[dict], prefer_uom: Optional[str] = None) -> Optional[dict]:
    """Pick first positive-price row, preferring a given UOM if specified."""
    if not items:
        return None
    if prefer_uom:
        for i in items:
            if (i.get("unitOfMeasure") == prefer_uom) and decimal(i.get("retailPrice") or 0) > 0:
                return i
    for i in items:
        if decimal(i.get("retailPrice") or 0) > 0:
            return i
    return items[0]

def _clean_row_to_allowed(r: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map common enterprise/Azure column variants into the canonical schema and drop all extras.
    We avoid inventing values; we only normalise where a close equivalent exists.
    """
    out = dict(_DEFAULTS)

    # Names
    out["serviceName"]  = pick_first(r, "serviceName", "ServiceName", "ProductName")
    out["productName"]  = pick_first(r, "productName", "ProductName")
    out["skuName"]      = pick_first(r, "skuName", "SkuName")
    out["meterName"]    = pick_first(r, "meterName", "MeterName")
    out["armSkuName"]   = pick_first(r, "armSkuName", "ArmSkuName")

    # Region / location
    _arm_region = pick_first(r, "armRegionName", "ArmRegionName")
    # Some EA sheets only have Region/Location; keep Location too (as-is) but prefer ARM region in armRegionName
    region_fallback = pick_first(r, "Region", "Location")
    out["location"] = pick_first(r, "Location", "location")  # optional free-text location
    out["armRegionName"] = arm_region(str(arm_region or region_fallback)) if (_arm_region or region_fallback) else None

    # Units & prices
    out["unitOfMeasure"] = pick_first(r, "unitOfMeasure", "UnitOfMeasure", "UnitOfMeasureDisplay")

    unit_price = pick_first(r, "unitPrice", "UnitPrice", "DiscountedPrice", "EffectiveUnitPrice")
    retail_price = pick_first(r, "retailPrice", "RetailPrice")  # sometimes absent in enterprise sheets
    # If only one price is present, mirror into the other so downstream is consistent
    if unit_price is None and retail_price is not None:
        unit_price = retail_price
    if retail_price is None and unit_price is not None:
        retail_price = unit_price
    out["unitPrice"] = unit_price
    out["retailPrice"] = retail_price

    # Currency
    out["currencyCode"] = pick_first(r, "currencyCode", "CurrencyCode", "Currency")

    # IDs & misc (copy if present; otherwise keep defaults)
    out["priceType"]           = pick_first(r, "priceType", "PriceType")
    out["effectiveStartDate"]  = pick_first(r, "effectiveStartDate", "EffectiveStartDate")
    out["effectiveEndDate"]    = pick_first(r, "effectiveEndDate", "EffectiveEndDate")
    out["meterId"]             = pick_first(r, "meterId", "MeterId")
    out["skuId"]               = pick_first(r, "skuId", "SkuId")
    out["productId"]           = pick_first(r, "productId", "ProductId")
    out["serviceId"]           = pick_first(r, "serviceId", "ServiceId")
    out["savingsPlan"]         = pick_first(r, "savingsPlan", "SavingsPlan")
    out["isPrimaryMeterRegion"]= pick_first(r, "isPrimaryMeterRegion", "IsPrimaryMeterRegion")
    out["serviceFamily"]       = pick_first(r, "serviceFamily", "ServiceFamily")
    out["type"]                = pick_first(r, "type", "Type")
    out["reservationTerm"]     = pick_first(r, "reservationTerm", "ReservationTerm")
    out["tierMinimumUnits"]    = pick_first(r, "tierMinimumUnits", "TierMinimumUnits")

    # Drop everything else by returning only the canonical keys
    return {k: out[k] for k in ALLOWED_HEADINGS}