from __future__ import annotations
from typing import Optional, List
from decimal import Decimal
import re

from ..pricing_sources import d

# ---------- Helpers ----------
def _arm_region(region_str: str) -> str:
    # "Australia East" -> "australiaeast"
    return region_str.strip().lower().replace(" ", "")

def _text_fields(i: dict) -> str:
    """Lower-cased concatenation of common descriptive fields."""
    return " ".join([
        (i.get("productName") or ""),
        (i.get("skuName") or ""),
        (i.get("meterName") or ""),
        (i.get("armSkuName") or ""),
    ]).lower()

def _pick_row_prefer_1h(items: List[dict], prefer_uom: str = "1 Hour") -> Optional[dict]:
    if not items:
        return None
    for i in items:
        if i.get("unitOfMeasure") == prefer_uom and d(i.get("retailPrice", 0)) > 0:
            return i
    for i in items:
        if d(i.get("retailPrice", 0)) > 0:
            return i
    return items[0]

def _per_count_from_text(uom: str, item: dict) -> Decimal:
    """
    Detect batch size like 10,000 / 100,000 even when the API doesn't put it in unitOfMeasure.
    Looks in unitOfMeasure and in meter/product/sku text; understands '10k', '100k', 'per 10k', etc.
    """
    s = (uom or "").lower().replace(",", "")
    txt = " ".join([
        item.get("meterName",""), item.get("productName",""), item.get("skuName","")
    ]).lower().replace(",", "")

    def detect(t: str) -> Optional[int]:
        if "100000" in t or "100k" in t: return 100000
        if "10000"  in t or "10k"  in t: return 10000
        if "1000"   in t or "1k"   in t: return 1000
        m = re.search(r"per\s+(\d+)\s*(k)?", t)  # e.g. "per 10k"
        if m:
            n = int(m.group(1))
            if m.group(2):  # "k"
                n *= 1000
            return n
        return None

    n = detect(s) or detect(txt)
    return d(n or 1)