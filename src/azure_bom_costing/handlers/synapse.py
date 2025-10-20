# =====================================================================================
# Azure Synapse Dedicated SQL Pool (Data Warehouse Units - DWU). Example component:
# {
#   "type": "synapse_sqlpool",
#   "sku": "DW1000c",
#   "hours_per_month": 200
# }
#
# Notes:
# • `sku` – Synapse Dedicated SQL Pool SKU, expressed in DWUs (e.g., DW100c, DW1000c, DW30000c).
# • `hours_per_month` – Runtime duration in hours; default 730 for full-month continuous operation.
# • Prices are resolved via Enterprise Price Sheet (if available) or Azure Retail API.
# • Billing unit: “1 Hour”, cost scales linearly with DWU count × hours.
# • Uses “Azure Synapse Analytics” service family and DWU-based meters.
# =====================================================================================
from decimal import Decimal
from typing import List, Dict

from ..helpers import _d, _arm_region
from ..pricing_sources import enterprise_lookup, retail_fetch_items
from ..types import Key

def _parse_dwu(sku: str) -> int:
    s = sku.lower().replace("dw", "").replace("c", "")
    try:
        return int(s)
    except Exception:
        return 100


def _is_synapse_dwu_row(i: dict) -> bool:
    """Accept only Dedicated SQL compute DWU meters; exclude storage/backup/serverless/etc."""
    txt = " ".join([
        i.get("serviceName",""), i.get("productName",""),
        i.get("skuName",""), i.get("meterName",""),
        i.get("unitOfMeasure","")
    ]).lower()

    if any(b in txt for b in [
        "backup", "storage", "snapshot", "serverless", "spark",
        "data processed", "data movement", "reserved"
    ]):
        return False

    return any(g in txt for g in ["dwu", "cdwu", "dedicated sql", "sql data warehouse"])


def _per_dwu_hour(unit_price: Decimal, row: dict) -> Decimal:
    """Normalize the row's price to a per-DWU-hour unit."""
    uom = (row.get("unitOfMeasure") or "").lower()
    txt = " ".join([
        row.get("productName",""), row.get("meterName",""),
        row.get("skuName",""), uom
    ]).lower()

    # Default assume per 1 DWU-hour
    denom = _d(1)

    # Common catalog patterns for *per 100 (c)DWU hours*
    if ("per 100" in txt or "100 dwu" in txt or "100 cdwu" in txt
            or uom in {"100 dwu hours", "100 cdwu hours", "100 dwu hour", "100 cdwu hour"}):
        denom = _d(100)

    return unit_price / denom


def _score_row(i: dict, arm_region: str) -> int:
    """Prefer correct region and hourly UOM; works after we filter with _is_synapse_dwu_row."""
    if _d(i.get("retailPrice", 0)) <= 0:
        return -999
    s = 0
    if (i.get("armRegionName") or "").lower() == arm_region: s += 5
    if (i.get("unitOfMeasure") or "").lower() in {
        "1 hour", "100 dwu hours", "100 cdwu hours", "100 dwu hour", "100 cdwu hour"
    }: s += 3
    return s


def price_synapse_sqlpool(component, region, currency, ent_prices: Dict[Key, Decimal]):
    sku   = component.get("sku", "DW100c")
    dwu   = _parse_dwu(sku)
    hours = _d(component.get("hours_per_month", 730))
    svc, uom = "Azure Synapse Analytics", "1 Hour"

    # ---- Enterprise price sheet (usually SKU-hour for the whole pool) ----
    ent = enterprise_lookup(ent_prices, svc, sku, region, uom)
    if ent is not None:
        # Enterprise rows for DW1000c are typically *per cluster-hour* (i.e., for 1000 DWU).
        # Convert to per-DWU-hr so math is consistent regardless of SKU:
        unit_per_dwu_hr = _d(ent) / _d(max(dwu, 1))
        picked_desc = "enterprise sheet"
    else:
        arm = _arm_region(region)

        filters = [
            (f"serviceName eq 'Azure Synapse Analytics' and armRegionName eq '{arm}' "
             "and priceType eq 'Consumption' and "
             "(contains(meterName,'DWU') or contains(meterName,'Dedicated SQL') "
             "or contains(productName,'Dedicated SQL') or contains(productName,'SQL Data Warehouse'))"),
            ("serviceName eq 'Azure Synapse Analytics' and priceType eq 'Consumption' and "
             "(contains(meterName,'DWU') or contains(productName,'Dedicated SQL') "
             "or contains(productName,'SQL Data Warehouse'))"),
        ]

        items: List[dict] = []
        for f in filters:
            try:
                items += retail_fetch_items(f, currency)
            except Exception:
                pass

        # Keep relevant compute rows with positive prices
        candidates = [i for i in items if _d(i.get("retailPrice", 0)) > 0 and _is_synapse_dwu_row(i)]
        if not candidates:
            return _d(0), f"Synapse SQLPool {sku} (unpriced)"

        # Prefer best-scored row; then normalize to per-DWU-hr
        candidates.sort(key=lambda r: _score_row(r, arm), reverse=True)
        # Compute per-DWU-hr and pick the lowest among well-scored candidates
        best_pd = None
        best_row = None
        for r in candidates[:10]:  # only look at top scored few
            pd = _per_dwu_hour(_d(r.get("retailPrice", 0)), r)
            if pd > 0 and (best_pd is None or pd < best_pd):
                best_pd, best_row = pd, r

        if best_pd is None:
            return _d(0), f"Synapse SQLPool {sku} (unpriced)"

        unit_per_dwu_hr = best_pd
        picked_desc = " / ".join(filter(None, [
            best_row.get("productName", ""), best_row.get("meterName", ""),
            best_row.get("unitOfMeasure", "")
        ]))

    total = unit_per_dwu_hr * _d(dwu) * hours
    return total, f"Synapse SQLPool {sku} @ {unit_per_dwu_hr}/DWU-hr × {dwu} DWU × {hours}h ({picked_desc})"