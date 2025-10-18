# =========================================================
# API Management
# component:
#   { "type":"api_management", "tier":"Developer|Basic|Standard|Premium|Consumption",
#     "gateway_units": 2, "hours_per_month":730, "calls_per_million": 50 }
# Notes:
#   - For Consumption we use per-request only (calls_per_million), no hourly base.
#   - For Dedicated tiers we price per-unit-hour + optional per-call if catalog exposes it.
# =========================================================
from decimal import Decimal
from typing import Dict

from ..helpers import _d, _dedup_merge, _pick, _arm_region
from ..pricing_sources import retail_fetch_items, retail_pick, enterprise_lookup
from ..types import Key


def price_api_management(component, region, currency, ent_prices: Dict[Key, Decimal]):
    tier = (component.get("tier") or "Developer").title()
    units = _d(component.get("gateway_units", 1))
    hours = _d(component.get("hours_per_month", 730))
    calls_m = _d(component.get("calls_per_million", 0))  # in millions

    arm = _arm_region(region)
    total = _d(0)

    if tier == "Consumption":
        # per 1M calls
        service, sku, uom = "API Management", "Requests", "1,000,000"
        ent = enterprise_lookup(ent_prices, service, sku, region, uom)
        if ent is not None:
            unit_per_m = ent
        else:
            flt = ("serviceName eq 'API Management' and priceType eq 'Consumption' "
                   "and (contains(meterName,'Requests') or contains(productName,'Requests'))")
            items = retail_fetch_items(flt, currency)
            row = retail_pick(items, uom) or _pick(items)
            unit_per_m = _d(row.get("retailPrice", 0)) if row else _d(0)
        total += unit_per_m * calls_m
        return total, f"APIM {tier} {calls_m}M req @ {unit_per_m}/1M"

    # Dedicated tiers: per-unit-hour
    service, uom = "API Management", "1 Hour"
    sku = f"{tier} Gateway Unit"
    ent = enterprise_lookup(ent_prices, service, sku, region, uom)
    if ent is not None:
        unit = ent
    else:
        filters = [
            (f"serviceName eq 'API Management' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
             f"and (contains(meterName,'Gateway') or contains(skuName,'{tier}'))"),
            ("serviceName eq 'API Management' and priceType eq 'Consumption' "
             f"and (contains(meterName,'Gateway') or contains(skuName,'{tier}'))"),
        ]
        row = _pick(_dedup_merge([retail_fetch_items(f, currency) for f in filters]), uom)
        unit = _d(row.get("retailPrice", 0)) if row else _d(0)
    total += unit * units * hours

    # Optional per-request line (if provided)
    if calls_m > 0:
        flt = ("serviceName eq 'API Management' and priceType eq 'Consumption' "
               "and (contains(meterName,'Requests') or contains(productName,'Requests'))")
        items = retail_fetch_items(flt, currency)
        row = retail_pick(items, "1,000,000") or _pick(items)
        unit_per_m = _d(row.get("retailPrice", 0)) if row else _d(0)
        total += unit_per_m * calls_m
        return total, f"APIM {tier} {units}x @ {unit}/hr × {hours}h + {calls_m}M req @ {unit_per_m}/1M"
    return total, f"APIM {tier} {units}x @ {unit}/hr × {hours}h"