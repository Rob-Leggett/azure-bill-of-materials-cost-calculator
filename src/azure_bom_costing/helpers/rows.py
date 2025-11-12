# helpers/rows.py
from typing import Iterable, List, Dict, Optional, Set
from decimal import Decimal

from .csv import arm_region
from .math import decimal

CsvRow = Dict[str, object]

def prefer_region(rows: List[CsvRow], region: str) -> List[CsvRow]:
    """Sort rows so exact armRegionName match appears first, then global/empty."""
    arm_l = arm_region(region).lower()
    def keyfn(r: CsvRow) -> int:
        row_arm = (str(r.get("armRegionName") or "")).lower()
        if row_arm == arm_l:
            return 0
        if row_arm == "":
            return 1
        return 2
    return sorted(rows, key=keyfn)

def pick_first(rows: List[CsvRow]) -> Optional[CsvRow]:
    return rows[0] if rows else None

def _text(i: CsvRow) -> str:
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

def _matches_any_equal(i: CsvRow, keys: List[str], value: str) -> bool:
    """Return True if any of the keys equals value (case-insensitive)."""
    tgt = (value or "").lower()
    for k in keys:
        if (str(i.get(k) or "")).lower() == tgt:
            return True
    return False

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
        if not _is_positive(i):
            continue

        # Required equals (straight keys)
        if any(not _eq(i, k, v) for k, v in required_equals.items()):
            continue

        # Allowed price types: accept either priceType or type
        if allowed_price_types:
            pt = (str(i.get("priceType") or "")).lower()
            typ = (str(i.get("type") or "")).lower()
            if (pt not in {t.lower() for t in allowed_price_types}) and (typ not in {t.lower() for t in allowed_price_types}):
                continue

        # UOM
        if required_uom and (str(i.get("unitOfMeasure") or "").lower() != uom_l):
            continue

        # Region hint (if provided): prefer rows whose armRegionName matches the hint
        if arm_region_l:
            row_arm = (str(i.get("armRegionName") or "")).lower()
            # If row has a region and it doesn't match, drop it. (Global rows often have empty armRegionName.)
            if row_arm and row_arm != arm_region_l:
                continue

        # Must contain tokens in canonical text
        if tokens:
            t = _text(i)
            if any(tok not in t for tok in tokens):
                continue

        out.append(i)
    return out