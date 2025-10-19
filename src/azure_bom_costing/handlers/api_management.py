# =====================================================================================
# Azure API Management (Dedicated and Consumption tiers). Example component:
# {
#   "type": "api_management",
#   "tier": "Standard",
#   "gateway_units": 2,
#   "hours_per_month": 730,
#   "calls_per_million": 50
# }
#
# Notes:
# • Models Azure API Management (APIM) pricing across dedicated and consumption tiers.
# • Consumption tier bills per million requests only.
# • Developer, Basic, Standard, and Premium tiers bill per Gateway Unit per hour, with optional per-request pricing.
#
# • Core parameters:
#     - `tier` → "Developer", "Basic", "Standard", "Premium", or "Consumption"
#     - `gateway_units` → Number of active gateway units (applies to dedicated tiers)
#     - `hours_per_month` → Hours of operation (default 730)
#     - `calls_per_million` → Request volume (millions of API calls)
#
# • Pricing structure:
#     - serviceName eq 'API Management'
#     - meterName or skuName contains "Gateway" for unit-hour rates
#     - meterName or productName contains "Requests" for per-million request rates
#     - unitOfMeasure = "1 Hour" or "1,000,000"
#
# • Enterprise lookup supported:
#     enterprise_lookup(ent_prices, "API Management", f"{tier} Gateway Unit", region, "1 Hour")
#     enterprise_lookup(ent_prices, "API Management", "Requests", region, "1,000,000")
# • Retail fallback queries Azure Retail Prices API for gateway and request meters.
#
# • Calculation:
#     if tier == "Consumption":
#         total_cost = calls_per_million × rate_per_million_requests
#     else:
#         total_cost = (gateway_units × hours_per_month × rate_per_hour)
#                     + (calls_per_million × rate_per_million_requests)
#
# • Example output:
#     APIM Standard 2x @ 0.41/hr × 730h + 50M req @ 0.03/1M = $620.50
#
# • Typical uses:
#     - Gateway/API proxy hosting for managed APIs
#     - Dedicated capacity tiers for enterprise environments
#     - Consumption tier for serverless or lightweight public endpoints
# • Developer tier is non-production and discounted but modeled identically for cost comparison.
# =====================================================================================
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