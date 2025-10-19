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
    """Extract numeric DWU count from SKU (e.g., 'DW1000c' → 1000)."""
    s = sku.lower().replace("dw", "").replace("c", "")
    try:
        return int(s)
    except Exception:
        return 100


def _is_synapse_dwu_row(i: dict) -> bool:
    """Keep only Dedicated SQL compute DWU meters (exclude storage, backup, serverless, etc.)."""
    txt = " ".join([
        i.get("serviceName", ""),
        i.get("productName", ""),
        i.get("skuName", ""),
        i.get("meterName", ""),
        i.get("unitOfMeasure", ""),
    ]).lower()

    # obvious non-compute or irrelevant meters
    bad = [
        "backup", "storage", "snapshot", "serverless", "provisioned throughput",
        "spark", "data processed", "data movement", "reserved"
    ]
    if any(b in txt for b in bad):
        return False

    # positive signals for dedicated sql/dwu
    good = ["dwu", "cdwu", "dedicated sql", "sql data warehouse"]
    return any(g in txt for g in good)


def _per_dwu_hour(unit_price: Decimal, row: dict) -> Decimal:
    """
    Normalize a retail row's unit price to a per-DWU-hour price.
    Common catalogs are per 100 (c)DWU hours.
    """
    uom = (row.get("unitOfMeasure") or "").lower()
    txt = " ".join([
        row.get("productName", ""), row.get("meterName", ""), row.get("skuName", ""), uom
    ]).lower()

    # default: assume already per 1 DWU hour (we'll override if tokens reveal "per 100")
    denom = _d(1)

    # tokens for "per 100 DWU/cDWU hours"
    tokens_100 = {
        "per 100", "100 dwu", "100 cdwu", "100 dwu hour", "100 cdwu hour",
        "100 dwu hours", "100 cdwu hours", "100 dwu-hr", "100 cdwu-hr", "100 dwu-hrs", "100 cdwu-hrs"
    }
    uoms_100 = {
        "100 dwu hours", "100 cdwu hours", "100 dwu hour", "100 cdwu hour"
    }

    if any(t in txt for t in tokens_100) or uom in uoms_100:
        denom = _d(100)

    # occasionally catalogs say "per cDWU hour" (cDWU ~= DWU for billing math here)
    # if we ever see "per 1000" (rare), you'd add another branch here.

    return unit_price / denom


def price_synapse_sqlpool(component, region, currency, ent_prices: Dict[Key, Decimal]):
    sku = component.get("sku", "DW100c")
    dwu = _parse_dwu(sku)
    hours = _d(component.get("hours_per_month", 730))
    service, uom = "Azure Synapse Analytics", "1 Hour"

    # --- Enterprise sheet first ---
    ent = enterprise_lookup(ent_prices, service, sku, region, uom)
    if ent is not None:
        # Most enterprise sheets quote the *SKU-hour* for the given DW size (e.g., DW1000c per hour),
        # not a per-DWU price. To avoid over/under-charging, divide by DWU to get per-DWU-hr.
        unit_per_dwu_hr = _d(ent) / _d(dwu) if dwu > 0 else _d(0)
    else:
        arm = _arm_region(region)
        filters = [
            (f"serviceName eq 'Azure Synapse Analytics' and armRegionName eq '{arm}' "
             "and priceType eq 'Consumption' and "
             "(contains(meterName,'DWU') or contains(meterName,'Dedicated SQL') "
             "or contains(productName,'Dedicated SQL') or contains(productName,'SQL Data Warehouse'))"),
            ("serviceName eq 'Azure Synapse Analytics' and priceType eq 'Consumption' "
             "and (contains(meterName,'DWU') or contains(productName,'Dedicated SQL') "
             "or contains(productName,'SQL Data Warehouse'))"),
        ]

        items: List[dict] = []
        for f in filters:
            try:
                items += retail_fetch_items(f, currency)
            except Exception:
                pass

        # Filter to relevant compute meters only, keep positive prices
        candidates = [i for i in items if _d(i.get("retailPrice", 0)) > 0 and _is_synapse_dwu_row(i)]
        if not candidates:
            return _d(0), f"Synapse SQLPool {sku} (unpriced)"

        # Compute per-DWU-hour for each candidate and pick a sensible minimum
        pairs = []
        for r in candidates:
            unit = _d(r.get("retailPrice", 0))
            pd = _per_dwu_hour(unit, r)
            if pd > 0:
                pairs.append((pd, r))

        if not pairs:
            return _d(0), f"Synapse SQLPool {sku} (unpriced)"

        # Guardrail: discard absurd outliers (e.g., > 0.20 AUD per DWU-hr ~ 20 AUD per 100 DWU-hr)
        sane = [p for p in pairs if p[0] < _d("0.20")]
        chosen = sane or pairs  # if guardrail removes all, fall back to the raw min
        chosen.sort(key=lambda t: t[0])

        unit_per_dwu_hr, picked = chosen[0]

    total = unit_per_dwu_hr * _d(dwu) * hours
    return total, f"Synapse SQLPool {sku} @ {unit_per_dwu_hr}/DWU-hr × {dwu} DWU × {hours}h"