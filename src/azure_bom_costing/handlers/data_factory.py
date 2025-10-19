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
from typing import Dict

from ..helpers import _d, _pick, _arm_region
from ..pricing_sources import enterprise_lookup, retail_fetch_items, retail_pick
from ..types import Key

def price_data_factory(component, region, currency, ent_prices: Dict[Key, Decimal]):
    arm = _arm_region(region)
    diu_hours = _d(component.get("diu_hours", 0))
    runs_1k  = _d(component.get("activity_runs_1k", 0))

    total = _d(0)

    # DIU hours
    if diu_hours > 0:
        service, uom = "Data Factory", "1 Hour"
        ent = enterprise_lookup(ent_prices, service, "Data Movement", region, uom)
        if ent is not None:
            unit = ent
        else:
            filters = [
                # Regioned, DIU / Data Movement
                (f"serviceName eq 'Data Factory' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                 "and (contains(meterName,'DIU') or contains(productName,'Data Movement'))"),
                # Global fallback
                ("serviceName eq 'Data Factory' and priceType eq 'Consumption' "
                 "and (contains(meterName,'DIU') or contains(productName,'Data Movement'))"),
            ]
            it = []
            for f in filters:
                try:
                    it += retail_fetch_items(f, currency)
                except Exception:
                    # If the API dislikes a filter form, just try the next one
                    pass
            row = _pick(it, uom)
            unit = _d(row.get("retailPrice", 0)) if row else _d(0)
        total += unit * diu_hours

    # Pipeline activity per 1k
    if runs_1k > 0:
        service, uom = "Data Factory", "1,000"
        ent = enterprise_lookup(ent_prices, service, "Pipeline Activities", region, uom)
        if ent is not None:
            unit = ent
        else:
            filters = [
                # Regioned, Pipeline (FIXED: removed extra ')')
                (f"serviceName eq 'Data Factory' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                 "and (contains(meterName,'Pipeline') or contains(productName,'Pipeline'))"),
                # Global fallback
                ("serviceName eq 'Data Factory' and priceType eq 'Consumption' "
                 "and (contains(meterName,'Pipeline') or contains(productName,'Pipeline'))"),
            ]
            it = []
            for f in filters:
                try:
                    it += retail_fetch_items(f, currency)
                except Exception:
                    pass
            row = retail_pick(it, uom) or _pick(it)
            unit = _d(row.get("retailPrice", 0)) if row else _d(0)
        total += unit * runs_1k

    return total, f"Data Factory (DIU:{diu_hours}h, Activities:{runs_1k}k)"