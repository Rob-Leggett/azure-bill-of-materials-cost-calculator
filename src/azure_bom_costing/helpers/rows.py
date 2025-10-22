# helpers/rows.py
from typing import Iterable, List, Dict, Optional
from decimal import Decimal

from .csv import arm_region
from .math import decimal

CsvRow = Dict[str, object]

def filter_rows(
        items: Iterable[CsvRow],
        required_equals: Dict[str, str],
        required_uom: Optional[str] = None,
        must_contain: Optional[List[str]] = None,
) -> List[CsvRow]:
    """
    Deterministic, CSV-only filtering:
      - exact equality on specific columns (e.g. serviceName, priceType)
      - optional exact UOM match (e.g. '1 Hour', '1 GB/Month', '10,000')
      - optional 'contains' tokens on the concatenated canonical text
      - positive retailPrice only
    """
    tokens = [t.lower() for t in (must_contain or [])]
    uom_l = (required_uom or "").lower()

    out: List[CsvRow] = []
    for i in items:
        if not _is_positive(i):
            continue
        if any(not _eq(i, k, v) for k, v in required_equals.items()):
            continue
        if required_uom and (str(i.get("unitOfMeasure") or "").lower() != uom_l):
            continue
        if tokens:
            t = _text(i)
            if any(tok not in t for tok in tokens):
                continue
        out.append(i)
    return out

def prefer_region(rows: List[CsvRow], region: str) -> List[CsvRow]:
    """Return rows sorted with exact armRegionName match first."""
    arm = arm_region(region).lower()
    return sorted(rows, key=lambda r: 0 if _eq(r, "armRegionName", arm) else 1)

def pick_first(rows: List[CsvRow]) -> Optional[CsvRow]:
    """Pick the first row (after prior stable filtering/sorting)."""
    return rows[0] if rows else None

def _text(i: CsvRow) -> str:
    # Minimal concatenation of canonical fields; no heuristics, just convenience.
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