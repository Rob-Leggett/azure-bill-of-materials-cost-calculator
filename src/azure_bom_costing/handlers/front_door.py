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

def _fd_is_noise(i: dict) -> bool:
    txt = " ".join([(i.get("productName") or ""), (i.get("skuName") or ""), (i.get("meterName") or "")]).lower()
    return any(k in txt for k in ["request", "data transfer", "egress", "waf", "rule set", "cdn"])

def _fd_is_baseish(i: dict) -> bool:
    txt = " ".join([(i.get("productName") or ""), (i.get("skuName") or ""), (i.get("meterName") or "")]).lower()
    return any(k in txt for k in ["fixed fee", "base fee", "base", "capacity", "capacity unit"])

def _score_fd_base(i: dict, arm_region: str, tier_l: str) -> int:
    if _d(i.get("retailPrice", 0)) <= 0:
        return -999
    txt = " ".join([
        i.get("serviceName",""), i.get("productName",""),
        i.get("skuName",""), i.get("meterName","")
    ]).lower()
    s = 0
    if (i.get("unitOfMeasure") or "") == "1 Hour": s += 6
    armn = (i.get("armRegionName") or "").lower()
    if armn == arm_region: s += 4
    if armn in ("", "global"): s += 2
    if "front door" in txt or "frontdoor" in txt: s += 3
    if tier_l in txt: s += 2
    if _fd_is_baseish(i): s += 4
    if _fd_is_noise(i): s -= 10
    return s

def _find_fd_base_unit(tier: str, arm_region: str, currency: str) -> Optional[Decimal]:
    tier_l = tier.lower()
    svc_names = ["Azure Front Door", "Frontdoor"]

    filters: List[str] = []
    # Regioned first (many SKUs still list Global, but try it)
    for svc in svc_names:
        filters += [
            (f"serviceName eq '{svc}' and armRegionName eq '{arm_region}' and priceType eq 'Consumption'"),
        ]
    # Global fallbacks — many base meters live here
    for svc in svc_names:
        filters += [
            (f"serviceName eq '{svc}' and priceType eq 'Consumption'"),
        ]

    batches = [retail_fetch_items(f, currency) for f in filters]
    items = _dedup_merge(batches)

    # Keep positive, base-ish, non-noise, hour-based rows — but don’t throw away useful rows too early
    cands = [i for i in items if _d(i.get("retailPrice", 0)) > 0 and not _fd_is_noise(i)]
    if not cands:
        return None

    # Prefer rows that look like the fixed/base fee and/or capacity; score, then pick best
    cands.sort(key=lambda i: _score_fd_base(i, arm_region, tier_l), reverse=True)

    # Strong preference: 1 Hour + base-ish
    strong = [i for i in cands if i.get("unitOfMeasure") == "1 Hour" and _fd_is_baseish(i)]
    row = strong[0] if strong else cands[0]
    return _d(row.get("retailPrice", 0))

def price_front_door(component, region, currency, ent_prices: Dict[Key, Decimal]):
    tier = (component.get("tier") or "Standard").title()   # "Standard" | "Premium"
    hours = _d(component.get("hours_per_month", 730))
    req_m = _d(component.get("requests_millions", 0))      # millions
    egress_gb = _d(component.get("egress_gb", 0))
    waf_policies = _d(component.get("waf_policies", 0))
    waf_rules = _d(component.get("waf_rules", 0))

    arm = _arm_region(region)
    total = _d(0)
    detail_bits: List[str] = []

    # ---------- BASE / CAPACITY (per hour) ----------
    # Try multiple likely enterprise SKU names before retail
    ent_svc, uom_hr = "Azure Front Door", "1 Hour"
    ent_candidates = [
        tier,                       # "Standard" / "Premium"
        f"{tier} Fixed Fee",
        f"{tier} Base Fee",
        f"{tier} Capacity",
        f"{tier} Capacity Unit",
    ]
    base_unit = None
    for sku_key in ent_candidates:
        ent = enterprise_lookup(ent_prices, ent_svc, sku_key, region, uom_hr)
        if ent is not None and _d(ent) > 0:
            base_unit = _d(ent)
            break

    if base_unit is None:
        base_unit = _find_fd_base_unit(tier, arm, currency)

    if base_unit is None or base_unit <= 0:
        # Be explicit rather than silently $0 — you can keep this or return $0 with a note
        return _d(0), f"Front Door {tier} (base not found; catalog uses classic/global wording)"

    total += base_unit * hours
    detail_bits.append(f"base:{base_unit}/hr×{hours}h")

    # ---------- REQUESTS (per 1M) ----------
    if req_m > 0:
        req_uom = "1,000,000"
        req_filters = [
            ("serviceName eq 'Azure Front Door' and priceType eq 'Consumption' "
             "and (contains(meterName,'Request') or contains(productName,'Request'))"),
            ("serviceName eq 'Frontdoor' and priceType eq 'Consumption' "
             "and (contains(meterName,'Request') or contains(productName,'Request'))"),
        ]
        req_items = _dedup_merge([retail_fetch_items(f, currency) for f in req_filters])
        row_req = retail_pick(req_items, req_uom) or _pick(req_items)
        if row_req:
            unit_req_m = _d(row_req.get("retailPrice", 0))
            total += unit_req_m * req_m
            detail_bits.append(f"req:{req_m}M@{unit_req_m}/1M")

    # ---------- EGRESS (per GB) ----------
    if egress_gb > 0:
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
        if row_egr:
            unit_dto = _d(row_egr.get("retailPrice", 0))
            total += unit_dto * egress_gb
            detail_bits.append(f"egress:{egress_gb}GB@{unit_dto}/GB")

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
        if row_wafp:
            unit_wafp = _d(row_wafp.get("retailPrice", 0))
            total += unit_wafp * waf_policies
            detail_bits.append(f"waf-policy:{waf_policies}@{unit_wafp}/mo")

    # ---------- WAF RULES (per rule / month) ----------
    if waf_rules > 0:
        wafr_uom = "1/Month"
        wafr_filters = [
            ("serviceName eq 'Azure Front Door' and priceType eq 'Consumption' "
             "and (contains(meterName,'WAF Rules') or contains(productName,'WAF Rules') "
             "or (contains(meterName,'Rule') and contains(productName,'WAF')))"),
            ("serviceName eq 'Frontdoor' and priceType eq 'Consumption' "
             "and (contains(meterName,'WAF Rules') or contains(productName,'WAF Rules') "
             "or (contains(meterName,'Rule') and contains(productName,'WAF')))"),
        ]
        wafr_items = _dedup_merge([retail_fetch_items(f, currency) for f in wafr_filters])
        row_wafr = retail_pick(wafr_items, wafr_uom) or _pick(wafr_items)
        if row_wafr:
            unit_wafr = _d(row_wafr.get("retailPrice", 0))
            total += unit_wafr * waf_rules
            detail_bits.append(f"waf-rules:{waf_rules}@{unit_wafr}/mo")

    return total, f"Front Door {tier} ({', '.join(detail_bits)})"