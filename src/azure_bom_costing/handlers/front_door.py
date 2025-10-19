# =====================================================================================
# Azure Front Door (Standard / Premium) + Web Application Firewall (WAF). Example:
# {
#   "type": "front_door",
#   "tier": "Standard|Premium",
#   "hours_per_month": 730,
#   "requests_millions": 200,
#   "egress_gb": 1000,
#   "waf_policies": 1,
#   "waf_rules": 10
# }
#
# Notes:
# • Models Azure Front Door (Std/Prem) with optional Web Application Firewall (WAF).
# • Components:
#     - Base Capacity (per hour)
#     - Requests (per 1,000,000)
#     - Data Transfer Out (per GB)
#     - WAF Policies (per policy/month)
#     - WAF Custom Rules (per rule/month)
# • `tier` – Standard or Premium; determines applicable SKU pricing.
# • Automatically retrieves regional retail rates; supports enterprise overrides.
# • Pricing units:
#     - Capacity: “1 Hour”
#     - Requests: “1,000,000”
#     - Data Transfer Out: “1 GB”
#     - WAF Policy: “1/Month”
#     - WAF Rule: “1/Month”
# • Recommended for production-scale workloads serving web traffic with global routing,
#   caching, TLS termination, and WAF protection.
# • Includes both control-plane (capacity) and data-plane (requests + egress) components.
# =====================================================================================
from decimal import Decimal
from typing import Dict, List, Optional

from ..helpers import _d, _pick, _arm_region, _dedup_merge
from ..pricing_sources import retail_pick, retail_fetch_items, enterprise_lookup
from ..types import Key

def _score_fd_base(i: dict, arm_region: str, tier_l: str) -> int:
    """Score base (hourly) Front Door rows: prefer correct tier, region, 1 Hour, and capacity/base wording."""
    if _d(i.get("retailPrice", 0)) <= 0:
        return -999

    txt = " ".join([
        i.get("serviceName",""), i.get("productName",""),
        i.get("skuName",""), i.get("meterName","")
    ]).lower()

    s = 0
    if (i.get("unitOfMeasure") or "") == "1 Hour": s += 6
    if (i.get("armRegionName") or "").lower() == arm_region: s += 5
    if "front door" in txt or "frontdoor" in txt: s += 4
    if tier_l in txt: s += 4
    if "capacity" in txt or "base" in txt: s += 3
    # penalize irrelevant signals
    bad = ["cdn", "azure cdn", "rule set", "waf policy", "waf rules", "requests", "data transfer"]
    if any(b in txt for b in bad): s -= 5
    return s


def _best(items: List[dict], scorer) -> Optional[dict]:
    items = [i for i in items if _d(i.get("retailPrice", 0)) > 0]
    if not items:
        return None
    items.sort(key=scorer, reverse=True)
    return items[0]


def price_front_door(component, region, currency, ent_prices: Dict[Key, Decimal]):
    tier = (component.get("tier") or "Standard").title()   # Standard | Premium
    hours = _d(component.get("hours_per_month", 730))
    req_m = _d(component.get("requests_millions", 0))       # millions
    egress_gb = _d(component.get("egress_gb", 0))
    waf_policies = _d(component.get("waf_policies", 0))
    waf_rules = _d(component.get("waf_rules", 0))

    arm = _arm_region(region)
    tier_l = tier.lower()
    total = _d(0)

    # ---------- BASE / CAPACITY (per hour) ----------
    service_base, uom_hr = "Azure Front Door", "1 Hour"
    ent_base = enterprise_lookup(ent_prices, service_base, tier, region, uom_hr)
    if ent_base is not None:
        base_unit = ent_base
    else:
        # Catalog is messy: try both 'Azure Front Door' and 'Frontdoor', regioned and global, various wording
        svc_names = ["Azure Front Door", "Frontdoor"]
        filters: List[str] = []
        for svc in svc_names:
            # Regioned
            filters += [
                (f"serviceName eq '{svc}' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                 f"and (contains(skuName,'{tier}') or contains(productName,'{tier}')) "
                 "and (contains(meterName,'Capacity') or contains(productName,'Capacity') or contains(meterName,'Base'))"),
                (f"serviceName eq '{svc}' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                 f"and (contains(skuName,'{tier}') or contains(productName,'{tier}'))"),
            ]
            # Global fallbacks (many FD rows omit region)
            filters += [
                (f"serviceName eq '{svc}' and priceType eq 'Consumption' "
                 f"and (contains(skuName,'{tier}') or contains(productName,'{tier}')) "
                 "and (contains(meterName,'Capacity') or contains(productName,'Capacity') or contains(meterName,'Base'))"),
                (f"serviceName eq '{svc}' and priceType eq 'Consumption' "
                 f"and (contains(skuName,'{tier}') or contains(productName,'{tier}'))"),
            ]

        batches = [retail_fetch_items(f, currency) for f in filters]
        items = _dedup_merge(batches)
        row_base = _best(items, lambda i: _score_fd_base(i, arm, tier_l))
        base_unit = _d(row_base.get("retailPrice", 0)) if row_base else _d(0)
    total += base_unit * hours

    # ---------- REQUESTS (per 1M) ----------
    if req_m > 0:
        # Requests are usually listed per 1,000,000; don’t tie to tier because some rows omit it
        req_uom = "1,000,000"
        req_filters = [
            ("serviceName eq 'Azure Front Door' and priceType eq 'Consumption' "
             "and (contains(meterName,'Request') or contains(productName,'Request'))"),
            ("serviceName eq 'Frontdoor' and priceType eq 'Consumption' "
             "and (contains(meterName,'Request') or contains(productName,'Request'))"),
        ]
        req_items = _dedup_merge([retail_fetch_items(f, currency) for f in req_filters])
        row_req = retail_pick(req_items, req_uom) or _pick(req_items)
        unit_req_m = _d(row_req.get("retailPrice", 0)) if row_req else _d(0)
        total += unit_req_m * req_m

    # ---------- EGRESS (per GB) ----------
    if egress_gb > 0:
        # Egress may say “Data Transfer Out”, “Outbound Data Transfer”, “Data Transfer to Internet”
        egr_uom = "1 GB"
        egr_filters = [
            ("serviceName eq 'Azure Front Door' and priceType eq 'Consumption' "
             "and (contains(meterName,'Data Transfer Out') or contains(meterName,'Outbound') "
             "or contains(productName,'Data Transfer Out') or contains(productName,'Outbound') "
             "or contains(productName,'Internet'))"),
            ("serviceName eq 'Frontdoor' and priceType eq 'Consumption' "
             "and (contains(meterName,'Data Transfer Out') or contains(meterName,'Outbound') "
             "or contains(productName,'Data Transfer Out') or contains(productName,'Outbound') "
             "or contains(productName,'Internet'))"),
        ]
        egr_items = _dedup_merge([retail_fetch_items(f, currency) for f in egr_filters])
        row_egr = retail_pick(egr_items, egr_uom) or _pick(egr_items)
        unit_dto = _d(row_egr.get("retailPrice", 0)) if row_egr else _d(0)
        total += unit_dto * egress_gb

    # ---------- WAF POLICY (per policy / month) ----------
    if waf_policies > 0:
        wafp_uom = "1/Month"
        wafp_filters = [
            ("serviceName eq 'Azure Front Door' and priceType eq 'Consumption' "
             "and (contains(meterName,'WAF Policy') or contains(productName,'WAF Policy'))"),
            ("serviceName eq 'Frontdoor' and priceType eq 'Consumption' "
             "and (contains(meterName,'WAF Policy') or contains(productName,'WAF Policy'))"),
        ]
        wafp_items = _dedup_merge([retail_fetch_items(f, currency) for f in wafp_filters])
        row_wafp = retail_pick(wafp_items, wafp_uom) or _pick(wafp_items)
        unit_wafp = _d(row_wafp.get("retailPrice", 0)) if row_wafp else _d(0)
        total += unit_wafp * waf_policies

    # ---------- WAF RULES (per rule / month) ----------
    if waf_rules > 0:
        wafr_uom = "1/Month"
        wafr_filters = [
            ("serviceName eq 'Azure Front Door' and priceType eq 'Consumption' "
             "and (contains(meterName,'WAF Rules') or contains(productName,'WAF Rules') "
             "or contains(meterName,'Rule') and contains(productName,'WAF'))"),
            ("serviceName eq 'Frontdoor' and priceType eq 'Consumption' "
             "and (contains(meterName,'WAF Rules') or contains(productName,'WAF Rules') "
             "or contains(meterName,'Rule') and contains(productName,'WAF'))"),
        ]
        wafr_items = _dedup_merge([retail_fetch_items(f, currency) for f in wafr_filters])
        row_wafr = retail_pick(wafr_items, wafr_uom) or _pick(wafr_items)
        unit_wafr = _d(row_wafr.get("retailPrice", 0)) if row_wafr else _d(0)
        total += unit_wafr * waf_rules

    return total, f"Front Door {tier} (base+req+egress+WAF)"