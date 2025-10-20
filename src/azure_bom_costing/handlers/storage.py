# =====================================================================================
# Azure Storage (Queue / Table / File Share / Blob). Example components:
#
# # Queue (10 million ops per month)
# { "type": "storage_queue", "operations_per_month": 10000000 }
#
# # Table (5 million ops per month)
# { "type": "storage_table", "operations_per_month": 5000000 }
#
# # File Share (Standard, 2TB)
# { "type": "fileshare", "tb": 2 }
#
# # Blob (Hot tier, LRS redundancy, 5TB, 1M transactions)
# { "type": "blob_storage", "sku": "Standard_LRS_Hot", "tb": 5, "transactions_per_month": 1000000 }
#
# Notes:
# • Covers all Azure Storage types commonly used outside Fabric or Synapse.
# • Queue/Table – charged per 10,000 transactions.
# • File Share – charged per GB-month of capacity (Standard tier only).
# • Blob – charged per GB-month by tier (Hot/Cool/Archive) and redundancy (LRS/GRS/ZRS/etc.).
# • Transactions (for Blob) add extra cost; batch size auto-detected (per 10k/100k).
# • Prices resolved via Enterprise Price Sheet or Retail API.
# • Billing units: "1 GB/Month", "10,000" transactions.
# =====================================================================================
from decimal import Decimal
from typing import Dict, Optional, List

from ..helpers import _arm_region, _pick, _d, _text_fields, _per_count_from_text, _has_price
from ..pricing_sources import retail_fetch_items, retail_pick, enterprise_lookup
from ..types import Key

def _ent_first(ent_prices: Dict[Key, Decimal], service: str, sku_candidates: List[str],
               region: str, uom: str) -> Optional[Decimal]:
    """Try several likely SkuName variants in enterprise sheet; return the first hit."""
    for sku in sku_candidates:
        ent = enterprise_lookup(ent_prices, service, sku, region, uom)
        if ent is not None:
            return ent
        # Some sheets omit armRegionName
        ent = enterprise_lookup(ent_prices, service, sku, "", uom)
        if ent is not None:
            return ent
    return None

# ---------- Queue ----------

def price_storage_queue(component, region, currency, ent_prices: Dict[Key, Decimal]):
    ops = _d(component.get("operations_per_month", 0))
    if ops <= 0:
        return _d(0), "Queue (0 ops)"
    arm = _arm_region(region)

    # Enterprise first (common SkuName variants)
    uom = "10,000"
    ent = _ent_first(
        ent_prices, "Storage",
        ["Queue Transactions", "Queue - Operations", "Queue Requests", "Queue"],
        region, uom
    )
    if ent is not None:
        unit_per_10k = ent
    else:
        items = retail_fetch_items(
            "serviceName eq 'Storage' "
            f"and armRegionName eq '{arm}' and priceType eq 'Consumption' "
            "and (contains(productName,'Queue') or contains(meterName,'Queue'))",
            currency
        )
        row = retail_pick(items, uom) or _pick(items)
        unit_per_10k = _d(row.get("retailPrice", 0)) if row else _d(0)

    return unit_per_10k * (ops / _d(10_000)), f"Queue ops:{ops} @ {unit_per_10k}/10k"


# ---------- Table ----------

def price_storage_table(component, region, currency, ent_prices: Dict[Key, Decimal]):
    ops = _d(component.get("operations_per_month", 0))
    if ops <= 0:
        return _d(0), "Table (0 ops)"
    arm = _arm_region(region)

    uom = "10,000"
    ent = _ent_first(
        ent_prices, "Storage",
        ["Table Transactions", "Table - Operations", "Table Requests", "Table"],
        region, uom
    )
    if ent is not None:
        unit_per_10k = ent
    else:
        items = retail_fetch_items(
            "serviceName eq 'Storage' "
            f"and armRegionName eq '{arm}' and priceType eq 'Consumption' "
            "and (contains(productName,'Table') or contains(meterName,'Table'))",
            currency
        )
        row = retail_pick(items, uom) or _pick(items)
        unit_per_10k = _d(row.get("retailPrice", 0)) if row else _d(0)

    return unit_per_10k * (ops / _d(10_000)), f"Table ops:{ops} @ {unit_per_10k}/10k"


# ---------- File Share (Standard capacity only) ----------

def price_fileshare(component, region, currency, ent_prices: Dict[Key, Decimal]):
    tb = _d(component.get("tb", 1))
    if tb <= 0:
        return _d(0), "File share (0 TB)"
    gb = tb * _d(1024)
    arm = _arm_region(region)

    service = "Storage"
    uom = "1 GB/Month"
    # Typical enterprise SkuName variants
    ent = _ent_first(
        ent_prices, service,
        ["File Data Stored", "Standard File Data Stored", "File Share Data Stored", "Files Data Stored"],
        region, uom
    )
    if ent is not None:
        unit_gbmo = ent
    else:
        items = retail_fetch_items(
            "serviceName eq 'Storage' "
            f"and armRegionName eq '{arm}' and priceType eq 'Consumption' "
            "and contains(meterName,'Data Stored') and contains(productName,'File')",
            currency
        )
        row = retail_pick(items, uom) or _pick(items)
        unit_gbmo = _d(row.get("retailPrice", 0)) if row else _d(0)

    return unit_gbmo * gb, f"File share {tb}TB @ {unit_gbmo}/GB-mo"


# ---------- Blob (capacity + optional transactions) ----------

def _pick_blob_storage_capacity(items: List[dict], tier: str, redundancy: str) -> Optional[dict]:
    """
    From a broad 'Storage' + region + 'Data Stored' set, pick the best match for tier & redundancy.
    Preference order:
      1) unitOfMeasure == '1 GB/Month' + BOTH tier & redundancy tokens present
      2) '1 GB/Month' + tier present
      3) Any UOM + BOTH tokens
      4) Any row with a positive price
    """
    if not items:
        return None

    tier_l = tier.lower()
    red_l = redundancy.lower().replace("-", "")

    def both_tokens(text: str) -> bool:
        t = text
        return (tier_l in t) and (red_l in t.replace("-", ""))

    def has_tier(text: str) -> bool:
        return tier_l in text

    # (1) 1GB/Month + BOTH tokens
    for i in items:
        if i.get("unitOfMeasure") == "1 GB/Month":
            txt = _text_fields(i).lower()
            if both_tokens(txt) and _has_price(i):
                return i

    # (2) 1GB/Month + TIER token
    for i in items:
        if i.get("unitOfMeasure") == "1 GB/Month":
            txt = _text_fields(i).lower()
            if has_tier(txt) and _has_price(i):
                return i

    # (3) Any UOM + BOTH tokens
    for i in items:
        txt = _text_fields(i).lower()
        if both_tokens(txt) and _has_price(i):
            return i

    # (4) First positive price
    for i in items:
        if _has_price(i):
            return i

    return None


def price_blob_storage(component, region, currency, ent_prices: Dict[Key, Decimal]):
    sku = component["sku"]  # e.g., "Standard_LRS_Hot"
    tier = "Hot" if "Hot" in sku else ("Cool" if "Cool" in sku else ("Archive" if "Archive" in sku else "Hot"))

    # Redundancy
    if   "RA-GZRS" in sku or "RAGZRS" in sku: redundancy = "RA-GZRS"
    elif "GZRS"   in sku:                      redundancy = "GZRS"
    elif "RA-GRS" in sku or "RAGRS" in sku:    redundancy = "RA-GRS"
    elif "ZRS"    in sku:                      redundancy = "ZRS"
    elif "GRS"    in sku:                      redundancy = "GRS"
    else:                                      redundancy = "LRS"

    tb = _d(component.get("tb", 1))
    gb = tb * _d(1024)

    service = "Storage"
    uom_cap = "1 GB/Month"

    # Enterprise capacity first (matches your sample like "LRS Hot Data Stored")
    ent_cap = _ent_first(
        ent_prices, service,
        [f"{redundancy} {tier} Data Stored", f"{redundancy} {tier} Blob Data Stored", f"{redundancy} {tier} Data Stored (Blob)"],
        region, uom_cap
    )
    if ent_cap is not None:
        cap_unit = ent_cap
    else:
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

        # Pick best match for tier & redundancy
        cap_row = _pick_blob_storage_capacity(cap_items, tier, redundancy)
        if not cap_row:
            raise RuntimeError(f"No capacity price for Storage {sku} (region={arm_region})")
        cap_unit = _d(cap_row.get("retailPrice", 0))

    total = cap_unit * gb

    # Blob transactions (optional)
    tx = _d(component.get("transactions_per_month", 0))
    if tx > 0:
        uom_tx_10k = "10,000"
        ent_tx = _ent_first(
            ent_prices, service,
            [f"{redundancy} {tier} Transactions", f"{redundancy} {tier} Operation", f"{redundancy} {tier} Requests"],
            region, uom_tx_10k
        )
        if ent_tx is not None:
            total += ent_tx * (tx / _d(10_000))
        else:
            arm_region = _arm_region(region)
            tx_filter = (
                "serviceName eq 'Storage' "
                f"and armRegionName eq '{arm_region}' "
                "and priceType eq 'Consumption' "
                "and contains(meterName,'Transactions')"
            )
            tx_items = retail_fetch_items(tx_filter, currency)
            tx_row = retail_pick(tx_items) or (tx_items[0] if tx_items else None)
            if tx_row and _has_price(tx_row):
                unit = _d(tx_row.get("retailPrice", 0))
                per = _per_count_from_text(tx_row.get("unitOfMeasure", "") or "", tx_row) or _d(10_000)
                total += unit * (tx / per)

    return total, f"Storage {sku} {tb}TB @ {cap_unit}/GB-mo (+tx)"