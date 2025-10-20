# =====================================================================================
# Azure Data Factory (simplified cost model). Example component:
# {
#   "type": "data_factory",
#   "diu_hours": 200,
#   "activity_runs_1k": 50
# }
#
# Notes:
# • Models Azure Data Factory consumption-based billing for:
#     - Data Integration Units (DIUs) — compute time for data movement & transformation.
#     - Pipeline Activity Runs — execution count for orchestrated workflows.
#
# • Core parameters:
#     - `diu_hours` → Total Data Integration Unit hours consumed.
#     - `activity_runs_1k` → Number of activity executions (in thousands).
#
# • Pricing structure:
#     - DIU Hours:
#         serviceName eq 'Data Factory'
#         meterName contains 'DIU' or 'Data Movement'
#         unitOfMeasure = "1 Hour"
#     - Pipeline Activities:
#         serviceName eq 'Data Factory'
#         meterName contains 'Pipeline'
#         unitOfMeasure = "1,000"
#
# • Enterprise lookup supported (serviceName: "Data Factory", SKU: "Data Movement").
# • Retail fallback queries via Azure Prices API if enterprise sheet unavailable.
# • Calculation:
#     total_cost = (DIU_hours × rate_per_hour) + (activity_runs_1k × rate_per_1k)
#
# • Example output:
#     Data Factory (DIU:200h, Activities:50k) ≈ $25.40
#
# • Typical uses:
#     - ETL workloads orchestrated in ADF.
#     - Data ingestion or transformation jobs between Azure and external data sources.
# • Simplified model excludes Data Flow, SSIS Integration Runtime, or VNET integration
#   costs (can be added separately if needed).
# =====================================================================================
from decimal import Decimal
from typing import Dict, List
from ..helpers import _d, _pick, _arm_region, _text_fields, _per_count_from_text
from ..pricing_sources import enterprise_lookup, retail_fetch_items, retail_pick
from ..types import Key

def _score_adf_row(i: dict, arm: str, want: str) -> int:
    """Score candidate ADF rows. want ∈ {'diu','pipeline'}."""
    price = _d(i.get("retailPrice", 0))
    if price <= 0:
        return -999
    txt = _text_fields(i)
    uom = (i.get("unitOfMeasure") or "").lower()
    s = 0
    if (i.get("armRegionName") or "").lower() == arm:
        s += 3
    if "data factory" in txt:
        s += 2
    if want == "diu":
        if "diu" in txt or "data movement" in txt:
            s += 5
        if "1 hour" in uom:
            s += 3
    else:  # pipeline
        if "pipeline" in txt:
            s += 5
        if "1,000" in uom or "1000" in uom or "1k" in uom:
            s += 3
    return s


def price_data_factory(component, region, currency, ent_prices: Dict[Key, Decimal]):
    arm = _arm_region(region)
    diu_hours = _d(component.get("diu_hours", 0))
    runs_1k  = _d(component.get("activity_runs_1k", 0))

    total = _d(0)
    details: List[str] = []

    # ---------- DIU hours ----------
    if diu_hours > 0:
        service, uom = "Data Factory", "1 Hour"
        # Enterprise first (commonly labeled "Data Movement")
        ent = enterprise_lookup(ent_prices, service, "Data Movement", region, uom)
        if ent is not None:
            unit = _d(ent)
        else:
            filters = [
                # Regioned
                (f"serviceName eq 'Data Factory' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                 "and (contains(meterName,'DIU') or contains(productName,'Data Movement') or contains(meterName,'Data Movement'))"),
                # Global
                ("serviceName eq 'Data Factory' and priceType eq 'Consumption' "
                 "and (contains(meterName,'DIU') or contains(productName,'Data Movement') or contains(meterName,'Data Movement'))"),
            ]
            items: List[dict] = []
            for f in filters:
                try:
                    items += retail_fetch_items(f, currency)
                except Exception:
                    pass

            row = retail_pick(items, uom)
            if not row and items:
                items.sort(key=lambda i: _score_adf_row(i, arm, "diu"), reverse=True)
                row = items[0]

            unit = _d(row.get("retailPrice", 0)) if row else _d(0)

        total += unit * diu_hours
        details.append(f"DIU:{diu_hours}h @ {unit}/h")

    # ---------- Pipeline activity per 1k ----------
    if runs_1k > 0:
        service, uom = "Data Factory", "1,000"
        ent = enterprise_lookup(ent_prices, service, "Pipeline Activities", region, uom)
        if ent is not None:
            unit = _d(ent)
        else:
            filters = [
                # Regioned
                (f"serviceName eq 'Data Factory' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                 "and (contains(meterName,'Pipeline') or contains(productName,'Pipeline'))"),
                # Global
                ("serviceName eq 'Data Factory' and priceType eq 'Consumption' "
                 "and (contains(meterName,'Pipeline') or contains(productName,'Pipeline'))"),
            ]
            items: List[dict] = []
            for f in filters:
                try:
                    items += retail_fetch_items(f, currency)
                except Exception:
                    pass

            row = retail_pick(items, uom) or _pick(items)
            if not row and items:
                items.sort(key=lambda i: _score_adf_row(i, arm, "pipeline"), reverse=True)
                row = items[0] if items else None

            # Normalize to per-1k in case UOM is odd (e.g., per 10k)
            unit = _d(row.get("retailPrice", 0)) if row else _d(0)
            per_count = _per_count_from_text(row.get("unitOfMeasure","") if row else "", row or {})
            if per_count and per_count != 1000:
                unit = unit * (_d(1000) / _d(per_count))

        total += unit * runs_1k
        details.append(f"Acts:{runs_1k}k @ {unit}/1k")

    return total, f"Data Factory ({', '.join(details) if details else 'no usage'})"