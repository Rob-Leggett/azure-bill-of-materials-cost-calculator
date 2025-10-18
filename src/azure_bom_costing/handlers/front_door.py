# =========================================================
# Azure Front Door + WAF
# component:
# { "type":"front_door", "tier":"Standard|Premium", "hours_per_month":730,
#   "requests_millions": 200, "egress_gb": 1000,
#   "waf_policies": 1, "waf_rules": 10 }
# =========================================================
from decimal import Decimal
from typing import Dict

from ..helpers import _d, _pick, _arm_region, _dedup_merge
from ..pricing_sources import retail_pick, retail_fetch_items, enterprise_lookup
from ..types import Key


def price_front_door(component, region, currency, ent_prices: Dict[Key, Decimal]):
    tier = (component.get("tier") or "Standard").title()
    hours = _d(component.get("hours_per_month", 730))
    req_m = _d(component.get("requests_millions", 0))
    egress_gb = _d(component.get("egress_gb", 0))
    waf_policies = _d(component.get("waf_policies", 0))
    waf_rules = _d(component.get("waf_rules", 0))

    arm = _arm_region(region)
    total = _d(0)

    # Base per hour (capacity)
    service, uom = "Azure Front Door", "1 Hour"
    ent = enterprise_lookup(ent_prices, service, f"{tier}", region, uom)
    if ent is None:
        filters = [
            (f"serviceName eq 'Azure Front Door' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
             f"and contains(skuName,'{tier}') and contains(meterName,'Capacity')"),
            ("serviceName eq 'Azure Front Door' and priceType eq 'Consumption' "
             f"and contains(skuName,'{tier}') and contains(meterName,'Capacity')"),
        ]
        row = _pick(_dedup_merge([retail_fetch_items(f, currency) for f in filters]), uom)
        base_unit = _d(row.get("retailPrice", 0)) if row else _d(0)
    else:
        base_unit = ent
    total += base_unit * hours

    # Requests per 1M
    if req_m > 0:
        flt = ("serviceName eq 'Azure Front Door' and priceType eq 'Consumption' "
               "and (contains(meterName,'Requests') or contains(productName,'Requests'))")
        row = retail_pick(retail_fetch_items(flt, currency), "1,000,000") or _pick(retail_fetch_items(flt, currency))
        unit_req_m = _d(row.get("retailPrice", 0)) if row else _d(0)
        total += unit_req_m * req_m

    # Data Transfer Out per GB (Internet)
    if egress_gb > 0:
        flt = ("serviceName eq 'Azure Front Door' and priceType eq 'Consumption' "
               "and (contains(meterName,'Data Transfer Out') or contains(productName,'Data Transfer Out'))")
        row = retail_pick(retail_fetch_items(flt, currency), "1 GB") or _pick(retail_fetch_items(flt, currency))
        unit_dto = _d(row.get("retailPrice", 0)) if row else _d(0)
        total += unit_dto * egress_gb

    # WAF policy per policy/month
    if waf_policies > 0:
        flt = ("serviceName eq 'Azure Front Door' and priceType eq 'Consumption' "
               "and contains(meterName,'WAF Policy')")
        row = retail_pick(retail_fetch_items(flt, currency), "1/Month") or _pick(retail_fetch_items(flt, currency))
        unit_pol = _d(row.get("retailPrice", 0)) if row else _d(0)
        total += unit_pol * waf_policies

    # WAF rules per rule/month (custom rules)
    if waf_rules > 0:
        flt = ("serviceName eq 'Azure Front Door' and priceType eq 'Consumption' "
               "and contains(meterName,'WAF Rules')")
        row = retail_pick(retail_fetch_items(flt, currency), "1/Month") or _pick(retail_fetch_items(flt, currency))
        unit_rule = _d(row.get("retailPrice", 0)) if row else _d(0)
        total += unit_rule * waf_rules

    return total, f"Front Door {tier} (base+req+egress+WAF)"