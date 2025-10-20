# =====================================================================================
# Azure Load Balancer (Standard) and Application Gateway v2. Example components:
#
# {
#   "type": "load_balancer",
#   "sku": "Standard",
#   "data_processed_gb": 500,
#   "rules": 5,
#   "hours_per_month": 730
# }
#
# {
#   "type": "app_gateway",
#   "capacity_units": 2,
#   "data_processed_gb": 1000,
#   "hours_per_month": 730
# }
#
# Notes:
# • Models Layer-4 Load Balancer and Layer-7 Application Gateway usage.
# • `data_processed_gb` – Total outbound data processed (billed per GB).
# • `rules` – Active Load Balancer rules (billed per rule-hour for some SKUs).
# • `capacity_units` – Application Gateway v2 capacity units (billed per hour).
# • `hours_per_month` – Number of active hours per month (default 730).
# • Billing units:
#     - Load Balancer Data: “1 GB”
#     - Load Balancer Rules: “1 Hour”
#     - App Gateway Capacity Units: “1 Hour”
#     - App Gateway Data: “1 GB”
# • Automatically fetches regional consumption rates from Azure Retail API.
# • Enterprise price sheet lookup supported for enterprise tenants if available.
# • Used to model web ingress costs when Front Door or WAF aren’t used directly.
# =====================================================================================
from decimal import Decimal
from typing import Dict, List, Optional

from ..helpers import _d, _arm_region, _per_count_from_text, _dedup_merge
from ..pricing_sources import retail_fetch_items, enterprise_lookup, retail_pick
from ..types import Key

def _ent_try(ent_prices: Dict[Key, Decimal], service: str, sku_candidates: List[str],
             region: str, uom_candidates: List[str]) -> Optional[Decimal]:
    """Try multiple SKU+UOM combos on enterprise sheet (with and without region)."""
    for sku in sku_candidates:
        for uom in uom_candidates:
            hit = enterprise_lookup(ent_prices, service, sku, region, uom)
            if hit is not None:
                return hit
            # some enterprise sheets omit region:
            hit = enterprise_lookup(ent_prices, service, sku, "", uom)
            if hit is not None:
                return hit
    return None


def _first_positive(items: List[dict], want_uom: Optional[str] = None) -> Optional[dict]:
    """Pick first row with positive price, optionally preferring a UOM."""
    if not items:
        return None
    if want_uom:
        for i in items:
            if (i.get("unitOfMeasure") == want_uom) and _d(i.get("retailPrice", 0)) > 0:
                return i
    for i in items:
        if _d(i.get("retailPrice", 0)) > 0:
            return i
    return None


# ---------------------------- Load Balancer ----------------------------

def price_load_balancer(component, region, currency, ent_prices: Dict[Key, Decimal]):
    sku = (component.get("sku") or "Standard").title()
    data_gb = _d(component.get("data_processed_gb", 0))
    rules   = _d(component.get("rules", 0))
    hours   = _d(component.get("hours_per_month", 730))
    arm = _arm_region(region)
    total = _d(0)

    # ---------- Data processed (per GB) ----------
    if data_gb > 0:
        svc, uom = "Load Balancer", "1 GB"
        ent = _ent_try(
            ent_prices,
            service=svc,
            sku_candidates=[
                f"{sku} Data Processed", "Data Processed", "Outbound Data Processed",
                "Processed Data"
            ],
            region=region,
            uom_candidates=[uom, "GB", "1 GB per Month"]  # normalize later if needed
        )
        if ent is not None:
            # normalize to per 1 GB if UOM implies a bundle size
            unit = ent / (_per_count_from_text("1 GB", {}) or _d(1))
        else:
            # Regioned first; then global; accept several wording variants
            filters = [
                (f"serviceName eq 'Load Balancer' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                 "and (contains(meterName,'Data Processed') or contains(meterName,'Outbound Data') "
                 "or contains(productName,'Data Processed') or contains(productName,'Outbound Data'))"),
                ("serviceName eq 'Load Balancer' and priceType eq 'Consumption' "
                 "and (contains(meterName,'Data Processed') or contains(meterName,'Outbound Data') "
                 "or contains(productName,'Data Processed') or contains(productName,'Outbound Data'))"),
            ]
            items = _dedup_merge([retail_fetch_items(f, currency) for f in filters])
            row = retail_pick(items, uom) or _first_positive(items, uom) or _first_positive(items)
            unit = _d(row.get("retailPrice", 0)) if row else _d(0)
            # normalize in case catalog used per 10 GB etc.
            per = _per_count_from_text((row.get("unitOfMeasure") or "") if row else "", row or {})
            if per not in (0, 1):
                unit = unit / per
        total += unit * data_gb

    # ---------- Rule hours (per hour per rule) ----------
    if rules > 0:
        svc, uom = "Load Balancer", "1 Hour"
        ent = _ent_try(
            ent_prices,
            service=svc,
            sku_candidates=[
                f"{sku} Rule Hours", "Rule Hours", "LB Rule Hours", "Rule"
            ],
            region=region,
            uom_candidates=[uom]
        )
        if ent is not None:
            unit = ent
        else:
            filters = [
                (f"serviceName eq 'Load Balancer' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                 "and (contains(meterName,'Rule') or contains(productName,'Rule'))"),
                ("serviceName eq 'Load Balancer' and priceType eq 'Consumption' "
                 "and (contains(meterName,'Rule') or contains(productName,'Rule'))"),
            ]
            items = _dedup_merge([retail_fetch_items(f, currency) for f in filters])
            row = retail_pick(items, uom) or _first_positive(items, uom) or _first_positive(items)
            unit = _d(row.get("retailPrice", 0)) if row else _d(0)
        total += unit * rules * hours

    return total, f"Load Balancer {sku} (data:{data_gb}GB, rules:{rules} × {hours}h)"


# ------------------------ Application Gateway v2 -----------------------

def price_app_gateway(component, region, currency, ent_prices: Dict[Key, Decimal]):
    # v2: capacity units + data processed GB
    cap_units = _d(component.get("capacity_units", 0))
    data_gb   = _d(component.get("data_processed_gb", 0))
    hours     = _d(component.get("hours_per_month", 730))
    arm = _arm_region(region)
    total = _d(0)

    # ---------- Capacity Units (per hour) ----------
    if cap_units > 0:
        svc, uom = "Application Gateway", "1 Hour"
        ent = _ent_try(
            ent_prices,
            service=svc,
            sku_candidates=["v2 Capacity Unit", "Capacity Unit", "Capacity Units"],
            region=region,
            uom_candidates=[uom]
        )
        if ent is not None:
            cu_unit = ent
        else:
            filters = [
                (f"serviceName eq 'Application Gateway' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                 "and (contains(meterName,'Capacity Unit') or contains(productName,'Capacity Unit'))"),
                ("serviceName eq 'Application Gateway' and priceType eq 'Consumption' "
                 "and (contains(meterName,'Capacity Unit') or contains(productName,'Capacity Unit'))"),
            ]
            items = _dedup_merge([retail_fetch_items(f, currency) for f in filters])
            row = retail_pick(items, uom) or _first_positive(items, uom) or _first_positive(items)
            cu_unit = _d(row.get("retailPrice", 0)) if row else _d(0)
        total += cu_unit * cap_units * hours

    # ---------- Data processed (per GB) ----------
    if data_gb > 0:
        svc, uom = "Application Gateway", "1 GB"
        ent = _ent_try(
            ent_prices,
            service=svc,
            sku_candidates=["Data Processed", "Outbound Data Processed", "Processed Data"],
            region=region,
            uom_candidates=[uom, "GB"]
        )
        if ent is not None:
            dp_unit = ent / (_per_count_from_text("1 GB", {}) or _d(1))
        else:
            filters = [
                (f"serviceName eq 'Application Gateway' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                 "and (contains(meterName,'Data Processed') or contains(meterName,'Outbound') "
                 "or contains(productName,'Data Processed') or contains(productName,'Outbound'))"),
                ("serviceName eq 'Application Gateway' and priceType eq 'Consumption' "
                 "and (contains(meterName,'Data Processed') or contains(meterName,'Outbound') "
                 "or contains(productName,'Data Processed') or contains(productName,'Outbound'))"),
            ]
            items = _dedup_merge([retail_fetch_items(f, currency) for f in filters])
            row = retail_pick(items, uom) or _first_positive(items, uom) or _first_positive(items)
            dp_unit = _d(row.get("retailPrice", 0)) if row else _d(0)
            per = _per_count_from_text((row.get("unitOfMeasure") or "") if row else "", row or {})
            if per not in (0, 1):
                dp_unit = dp_unit / per
        total += dp_unit * data_gb

    return total, f"App Gateway v2 (CU:{cap_units} × {hours}h, data:{data_gb}GB)"