from decimal import Decimal
from typing import Dict, Optional, List

from .common import _text_fields, _arm_region, _per_count_from_text
from ..pricing_sources import d, enterprise_lookup, retail_fetch_items, retail_pick
from ..types import Key

# ---------- Storage (Blob) ----------
def _pick_storage_capacity(items: List[dict], tier: str, redundancy: str) -> Optional[dict]:
    """
    From a broad 'Storage' + region + 'Data Stored' set, pick the best match for tier & redundancy.
    Preference order:
      1) unitOfMeasure == '1 GB/Month' + BOTH tier & redundancy tokens present
      2) '1 GB/Month' + tier present
      3) any UOM + BOTH tokens
      4) any row with a positive price
    """
    if not items:
        return None

    tier_l = tier.lower()     # 'hot' | 'cool' | 'archive'
    red_l  = redundancy.lower()  # 'lrs' | 'grs' | 'zrs' | 'ragrs' | 'gzrs' | 'ragzrs' (etc.)

    def norm(s: str) -> str:
        return s.lower().replace("-", "")

    red_l = norm(red_l)

    def both_tokens(text: str) -> bool:
        t = text
        return (tier_l in t) and (red_l in norm(t))

    def has_tier(text: str) -> bool:
        return tier_l in text

    # (1) 1GB/Month + BOTH tokens
    for i in items:
        if i.get("unitOfMeasure") == "1 GB/Month":
            txt = _text_fields(i)
            if both_tokens(txt) and d(i.get("retailPrice", 0)) > 0:
                return i

    # (2) 1GB/Month + TIER token
    for i in items:
        if i.get("unitOfMeasure") == "1 GB/Month":
            txt = _text_fields(i)
            if has_tier(txt) and d(i.get("retailPrice", 0)) > 0:
                return i

    # (3) Any UOM + BOTH tokens
    for i in items:
        txt = _text_fields(i)
        if both_tokens(txt) and d(i.get("retailPrice", 0)) > 0:
            return i

    # (4) Fallback: first positive price
    for i in items:
        if d(i.get("retailPrice", 0)) > 0:
            return i

    return None

def price_storage(component, region, currency, ent_prices: Dict[Key, Decimal]):
    sku = component["sku"]  # e.g., "Standard_LRS_Hot"
    tier = "Hot" if "Hot" in sku else ("Cool" if "Cool" in sku else ("Archive" if "Archive" in sku else "Hot"))
    # Accept broader redundancy flavours
    if   "RA-GZRS" in sku or "RAGZRS" in sku: redundancy = "RA-GZRS"
    elif "GZRS"   in sku:                      redundancy = "GZRS"
    elif "RA-GRS" in sku or "RAGRS" in sku:    redundancy = "RA-GRS"
    elif "ZRS"    in sku:                      redundancy = "ZRS"
    elif "GRS"    in sku:                      redundancy = "GRS"
    else:                                      redundancy = "LRS"

    tb = d(component.get("tb", 1))
    gb = tb * d(1024)

    service = "Storage"
    uom_cap = "1 GB/Month"

    ent_key_sku = f"{redundancy} {tier} Data Stored"
    ent = enterprise_lookup(ent_prices, service, ent_key_sku, region, uom_cap)
    if ent is None:
        arm_region = _arm_region(region)
        cap_filter = (
            "serviceName eq 'Storage' "
            f"and armRegionName eq '{arm_region}' "
            "and priceType eq 'Consumption' "
            "and contains(meterName,'Data Stored')"
        )
        cap_items = retail_fetch_items(cap_filter, currency)
        if not cap_items:
            cap_filter2 = (
                "serviceName eq 'Storage' "
                f"and armRegionName eq '{arm_region}' "
                "and priceType eq 'Consumption' "
                "and contains(productName,'Data Stored')"
            )
            cap_items = retail_fetch_items(cap_filter2, currency)

        cap_row = _pick_storage_capacity(cap_items, tier=tier, redundancy=redundancy)
        if not cap_row:
            raise RuntimeError(f"No capacity price for Storage {sku} (region={arm_region})")
        cap_unit = d(cap_row.get("retailPrice", 0))
    else:
        cap_unit = ent

    total = cap_unit * gb

    # Transactions (rough)
    tx = d(component.get("transactions_per_month", 0))
    if tx > 0:
        uom_tx_10k = "10,000"
        ent_tx = enterprise_lookup(ent_prices, service, f"{redundancy} {tier} Transactions", region, uom_tx_10k)
        if ent_tx is None:
            arm_region = _arm_region(region)
            tx_filter = (
                "serviceName eq 'Storage' "
                f"and armRegionName eq '{arm_region}' "
                "and priceType eq 'Consumption' "
                "and contains(meterName,'Transactions')"
            )
            tx_items = retail_fetch_items(tx_filter, currency)
            tx_row = retail_pick(tx_items) or (tx_items[0] if tx_items else None)
            if tx_row:
                unit = d(tx_row.get("retailPrice", 0))
                uom = (tx_row.get("unitOfMeasure", "") or "")
                per = _per_count_from_text(uom, tx_row)
                total += unit * (tx / per)
        else:
            total += ent_tx * (tx / d(10000))

    return total, f"Storage {sku} {tb}TB @ {cap_unit}/GB-mo (+tx)"