from __future__ import annotations

from typing import Dict, Optional, Any, Iterable, List, Set
from decimal import Decimal
import json

# If these live next to this file, import directly; otherwise adjust path.
from .math import decimal  # used for price parsing

# -------------------------------------------------------------------
# Canonical CSV schema for Azure pricing rows
# -------------------------------------------------------------------
ALLOWED_HEADINGS = (
    "serviceName", "productName", "skuName", "meterName", "unitOfMeasure",
    "retailPrice", "currencyCode", "armRegionName", "priceType", "effectiveStartDate",
    "meterId", "skuId", "productId", "effectiveEndDate", "unitPrice",
    "serviceId", "location", "savingsPlan", "isPrimaryMeterRegion", "serviceFamily",
    "type", "reservationTerm", "armSkuName", "tierMinimumUnits",
)

# Default row skeleton: ensure every cleaned row always has these keys
_DEFAULTS: Dict[str, Optional[str]] = {k: None for k in ALLOWED_HEADINGS}


# -------------------------------------------------------------------
# Region helpers
# -------------------------------------------------------------------
def arm_region(region_str: str) -> str:
    """
    Map human region label ('Australia East') -> ARM format ('australiaeast').
    Empty-safe.
    """
    return (region_str or "").strip().lower().replace(" ", "")


# -------------------------------------------------------------------
# Cleaning / normalization entry points
# -------------------------------------------------------------------
def clean_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert arbitrary input rows (Retail API, Enterprise CSV) to the canonical schema.
    - We never invent values; we only normalize where obvious equivalents exist.
    - Non-scalar values (lists/dicts) are JSON-encoded; callables are dropped.
    """
    return [_clean_row_to_allowed(r) for r in rows]


def dedup_merge(lists: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Merge lists of already-cleaned rows, removing duplicates.

    De-dup key preference:
      1) meterId if present (globally unique)
      2) otherwise, a tuple of (serviceName, skuName, meterName, unitOfMeasure, armRegionName)
    """
    seen: set = set()
    out: List[Dict[str, Any]] = []

    for lst in lists:
        for r in lst or []:
            key = r.get("meterId") or (
                r.get("serviceName"),
                r.get("skuName"),
                r.get("meterName"),
                r.get("unitOfMeasure"),
                r.get("armRegionName"),
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(r)

    return out


# -------------------------------------------------------------------
# Small utilities used by the cleaner
# -------------------------------------------------------------------
def pick_first_dict(d: Dict[str, Any], *keys: str) -> Optional[Any]:
    """Return the first key in *keys* that exists in dict d and is not blank."""
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


def pick(items: List[dict], prefer_uom: Optional[str] = None) -> Optional[dict]:
    """
    Pick the first positive-price row, preferring a given UOM if specified.
    (Kept for compatibility with existing callers.)
    """
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


def _to_scalar(v: Any) -> Optional[str]:
    """
    Ensure a CSV-safe scalar:
      - None/"" -> None
      - list/dict -> compact JSON string
      - callable -> None (drop leaked function reprs)
      - other -> str(v)
    """
    if v in (None, ""):
        return None
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False, separators=(",", ":"))
    if callable(v):
        return None
    return str(v)


# -------------------------------------------------------------------
# Main normalization function
# -------------------------------------------------------------------
def _clean_row_to_allowed(r: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map common Azure column variants into the canonical schema and drop all extras.
    Symmetry:
      - If only unitPrice exists, copy it into retailPrice (and vice versa)
      - Region normalization prefers armRegionName; falls back to Region/Location
    """
    out = dict(_DEFAULTS)

    # ---- Canonical names ----
    out["serviceName"] = pick_first_dict(r, "serviceName", "ServiceName", "ProductName")
    out["productName"] = pick_first_dict(r, "productName", "ProductName")
    out["skuName"] = pick_first_dict(r, "skuName", "SkuName")
    out["meterName"] = pick_first_dict(r, "meterName", "MeterName")
    out["armSkuName"] = pick_first_dict(r, "armSkuName", "ArmSkuName")

    # ---- Region & location (ensure no function-leak; use _arm_region_val var) ----
    _arm_region_val = pick_first_dict(r, "armRegionName", "ArmRegionName")
    region_fallback = pick_first_dict(r, "Region", "Location")
    out["location"] = pick_first_dict(r, "Location", "location")  # optional free-text
    out["armRegionName"] = (
        arm_region(str(_arm_region_val or region_fallback))
        if (_arm_region_val or region_fallback)
        else None
    )

    # ---- Units & prices ----
    out["unitOfMeasure"] = pick_first_dict(r, "unitOfMeasure", "UnitOfMeasure", "UnitOfMeasureDisplay")

    unit_price = pick_first_dict(r, "unitPrice", "UnitPrice", "DiscountedPrice", "EffectiveUnitPrice")
    retail_price = pick_first_dict(r, "retailPrice", "RetailPrice")

    # Keep both in sync when only one exists; helps downstream logic
    if unit_price is None and retail_price is not None:
        unit_price = retail_price
    if retail_price is None and unit_price is not None:
        retail_price = unit_price

    out["unitPrice"] = unit_price
    out["retailPrice"] = retail_price

    # ---- Currency ----
    out["currencyCode"] = pick_first_dict(r, "currencyCode", "CurrencyCode", "Currency")

    # ---- IDs & misc ----
    out["priceType"] = pick_first_dict(r, "priceType", "PriceType")
    out["effectiveStartDate"] = pick_first_dict(r, "effectiveStartDate", "EffectiveStartDate")
    out["effectiveEndDate"] = pick_first_dict(r, "effectiveEndDate", "EffectiveEndDate")
    out["meterId"] = pick_first_dict(r, "meterId", "MeterId")
    out["skuId"] = pick_first_dict(r, "skuId", "SkuId")
    out["productId"] = pick_first_dict(r, "productId", "ProductId")
    out["serviceId"] = pick_first_dict(r, "serviceId", "ServiceId")
    out["savingsPlan"] = pick_first_dict(r, "savingsPlan", "SavingsPlan")
    out["isPrimaryMeterRegion"] = pick_first_dict(r, "isPrimaryMeterRegion", "IsPrimaryMeterRegion")
    out["serviceFamily"] = pick_first_dict(r, "serviceFamily", "ServiceFamily")
    out["type"] = pick_first_dict(r, "type", "Type")
    out["reservationTerm"] = pick_first_dict(r, "reservationTerm", "ReservationTerm")
    out["tierMinimumUnits"] = pick_first_dict(r, "tierMinimumUnits", "TierMinimumUnits")

    # ---- Ensure CSV-safe scalars ----
    for k in ALLOWED_HEADINGS:
        out[k] = _to_scalar(out[k])

    # Return only canonical keys
    return {k: out[k] for k in ALLOWED_HEADINGS}


# -------------------------------------------------------------------
# Row-level helpers (filtering / sorting)
# -------------------------------------------------------------------
CsvRow = Dict[str, object]


def prefer_region(rows: List[CsvRow], region: str) -> List[CsvRow]:
    """
    Stable-sort rows so that the given region appears first, then global/empty, then others.
    """
    arm_l = arm_region(region).lower()

    def keyfn(r: CsvRow) -> int:
        row_arm = (str(r.get("armRegionName") or "")).lower()
        if row_arm == arm_l:
            return 0
        if row_arm == "":
            return 1
        return 2

    return sorted(rows, key=keyfn)


def pick_first_row(rows: List[CsvRow]) -> Optional[CsvRow]:
    """Pick the first row or None."""
    return rows[0] if rows else None


def _text(i: CsvRow) -> str:
    """
    Canonical text for token matching across common name fields.
    """
    return " ".join([
        str(i.get("serviceName") or ""),
        str(i.get("productName") or ""),
        str(i.get("skuName") or ""),
        str(i.get("meterName") or ""),
        str(i.get("armSkuName") or ""),
    ]).lower()


def _price(i: CsvRow) -> Decimal:
    return decimal(i.get("retailPrice") or 0)


def _is_positive(i: CsvRow) -> bool:
    return _price(i) > 0


def _eq(i: CsvRow, key: str, val: str) -> bool:
    return (str(i.get(key) or "")).lower() == (val or "").lower()


def filter_rows(
        items: Iterable[CsvRow],
        required_equals: Dict[str, str],
        required_uom: Optional[str] = None,
        must_contain: Optional[List[str]] = None,
        allowed_price_types: Optional[Set[str]] = None,  # e.g. {"Consumption","DevTestConsumption"}
        region_hint: Optional[str] = None,               # human-readable region, e.g. "Australia East"
) -> List[CsvRow]:
    """
    Deterministic CSV-based filter:
      - exact equality on provided columns
      - accept price type from either 'priceType' or 'type'
      - optional exact UOM match
      - optional tokens on canonical text
      - positive retailPrice
      - optional region hint mapped via arm_region to match armRegionName
    """
    tokens = [t.lower() for t in (must_contain or []) if t]
    uom_l = (required_uom or "").lower()
    arm_region_l = arm_region(region_hint).lower() if region_hint else None

    out: List[CsvRow] = []
    for i in items:
        # positive price only
        if not _is_positive(i):
            continue

        # required equals (straight keys)
        if any(not _eq(i, k, v) for k, v in required_equals.items()):
            continue

        # allowed price types: accept either priceType or type
        if allowed_price_types:
            pt = (str(i.get("priceType") or "")).lower()
            typ = (str(i.get("type") or "")).lower()
            allowed = {t.lower() for t in allowed_price_types}
            if (pt not in allowed) and (typ not in allowed):
                continue

        # UOM
        if required_uom and (str(i.get("unitOfMeasure") or "").lower() != uom_l):
            continue

        # Region hint (if provided): drop rows that specify a *different* region
        # (Global rows often have empty armRegionName -> keep them)
        if arm_region_l:
            row_arm = (str(i.get("armRegionName") or "")).lower()
            if row_arm and row_arm != arm_region_l:
                continue

        # Must contain tokens across canonical text
        if tokens and any(tok not in _text(i) for tok in tokens):
            continue

        out.append(i)

    return out


# -------------------------------------------------------------------
# Backwards-compat exports (so old code that imported from helpers.rows works)
# -------------------------------------------------------------------
# Many call-sites expect `pick_first` (row-level) from the old rows.py.
# We export a name that matches that expectation while keeping a separate
# pick_first_dict() for the cleaner to avoid name collisions.
pick_first = pick_first_row