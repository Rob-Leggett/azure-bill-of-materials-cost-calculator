# =========================================================
# Azure Functions (Consumption)
# component:
#   { "type":"functions", "gb_seconds": 250000000, "executions": 200000000 }
#   (pass GB-seconds total and raw execution count; both optional)
# =========================================================
from decimal import Decimal
from typing import Dict

from ..helpers import _pick, _arm_region
from ..pricing_sources import enterprise_lookup, retail_pick, retail_fetch_items
from ..types import Key


def price_functions(component, region, currency, ent_prices: Dict[Key, Decimal]):
    gb_seconds = _d(component.get("gb_seconds", 0))
    execs = _d(component.get("executions", 0))
    arm = _arm_region(region)
    total = _d(0)

    # Execution time per GB-second (billed per million GB-seconds in catalog)
    if gb_seconds > 0:
        service, sku, uom = "Functions", "Execution Time", "1,000,000 GB Seconds"
        ent = enterprise_lookup(ent_prices, service, sku, region, uom)
        if ent is None:
            flt = (f"serviceName eq 'Functions' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                   "and contains(meterName,'Execution Time')")
            row = retail_pick(retail_fetch_items(flt, currency), uom) or _pick(retail_fetch_items(flt, currency))
            unit_per_mgbsec = _d(row.get("retailPrice", 0)) if row else _d(0)
        else:
            unit_per_mgbsec = ent
        total += unit_per_mgbsec * (gb_seconds / _d(1_000_000))

    # Executions per 1M
    if execs > 0:
        service, sku, uom = "Functions", "Executions", "1,000,000"
        ent = enterprise_lookup(ent_prices, service, sku, region, uom)
        if ent is None:
            flt2 = ("serviceName eq 'Functions' and priceType eq 'Consumption' "
                    "and contains(meterName,'Executions')")
            row2 = retail_pick(retail_fetch_items(flt2, currency), uom) or _pick(retail_fetch_items(flt2, currency))
            unit_per_m = _d(row2.get("retailPrice", 0)) if row2 else _d(0)
        else:
            unit_per_m = ent
        total += unit_per_m * (execs / _d(1_000_000))

    return total, "Functions (GB-s + execs)"