# =====================================================================================
# Azure Private Networking (Private Endpoints + NAT Gateway). Example component:
# {
#   "type": "private_networking",
#   "private_endpoints": 6,
#   "pe_hours": 730,
#   "nat_gateways": 2,
#   "nat_hours": 730,
#   "nat_data_gb": 1500
# }
#
# Notes:
# • Models both Private Endpoints and NAT Gateways.
# • `private_endpoints` – Number of Private Endpoints (per-hour billing).
# • `pe_hours` – Hours per month each endpoint is active (default 730).
# • `nat_gateways` – Number of NAT Gateways provisioned.
# • `nat_hours` – Hours per month each NAT Gateway runs.
# • `nat_data_gb` – Outbound data processed via NAT (billed per GB).
# • Billing units:
#     - Private Endpoint: “1 Hour”
#     - NAT Gateway Hours: “1 Hour”
#     - NAT Gateway Data: “1 GB”
# • Used to account for VNet isolation and egress routing costs in secure environments.
# • Rates fetched from Azure Retail API (no enterprise-specific pricing usually available).
# =====================================================================================
from decimal import Decimal
from typing import Dict, Optional, List

from ..helpers import _d, _pick, _arm_region, _dedup_merge, _has_price
from ..pricing_sources import retail_fetch_items, retail_pick, enterprise_lookup
from ..types import Key

def _ent_first(ent_prices: Dict[Key, Decimal], service: str, sku_candidates: List[str],
               region: str, uom: str) -> Optional[Decimal]:
    """Try several likely SKU names in the enterprise sheet, return the first hit."""
    for sku in sku_candidates:
        ent = enterprise_lookup(ent_prices, service, sku, region, uom)
        if ent is not None:
            return ent
    return None


def price_private_networking(component, region, currency, ent_prices: Dict[Key, Decimal]):
    arm = _arm_region(region)
    total = _d(0)

    # ---------- Private Endpoints (per hour) ----------
    pe_cnt   = _d(component.get("private_endpoints", 0))
    pe_hours = _d(component.get("pe_hours", 730))

    if pe_cnt > 0:
        service_pe, uom_hr = "Private Link", "1 Hour"

        # 1) Enterprise sheet (common SKUs)
        ent_pe = _ent_first(
            ent_prices,
            service_pe,
            ["Private Endpoint", "Private Endpoints", "Private Endpoint (per hour)"],
            region,
            uom_hr,
        )

        if ent_pe is not None:
            unit_pe_hr = ent_pe
        else:
            # 2) Retail fallbacks — regioned then global; accept meterName/productName
            flts = [
                (f"serviceName eq 'Private Link' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                 "and (contains(meterName,'Private Endpoint') or contains(productName,'Private Endpoint'))"),
                ("serviceName eq 'Private Link' and priceType eq 'Consumption' "
                 "and (contains(meterName,'Private Endpoint') or contains(productName,'Private Endpoint'))"),
            ]
            items = _dedup_merge([retail_fetch_items(f, currency) for f in flts])
            row = retail_pick([i for i in items if i.get("unitOfMeasure") == uom_hr and _has_price(i)], uom_hr)
            if not row:
                row = _pick([i for i in items if _has_price(i)])
            unit_pe_hr = _d(row.get("retailPrice", 0)) if row else _d(0)

        total += unit_pe_hr * pe_cnt * pe_hours

    # ---------- NAT Gateway (per hour + data processed) ----------
    nat_cnt   = _d(component.get("nat_gateways", 0))
    nat_hours = _d(component.get("nat_hours", 730))
    nat_gb    = _d(component.get("nat_data_gb", 0))

    if nat_cnt > 0:
        service_nat, uom_hr, uom_gb = "NAT Gateway", "1 Hour", "1 GB"

        # Base hours
        ent_nat_hr = _ent_first(
            ent_prices,
            service_nat,
            ["Gateway Hours", "NAT Gateway Hours", "NAT Gateway"],
            region,
            uom_hr,
        )

        if ent_nat_hr is not None:
            unit_nat_hr = ent_nat_hr
        else:
            flts_base = [
                (f"serviceName eq 'NAT Gateway' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                 "and (contains(meterName,'Gateway Hours') or contains(productName,'Gateway Hours'))"),
                ("serviceName eq 'NAT Gateway' and priceType eq 'Consumption' "
                 "and (contains(meterName,'Gateway Hours') or contains(productName,'Gateway Hours'))"),
            ]
            items_b = _dedup_merge([retail_fetch_items(f, currency) for f in flts_base])
            row_b = retail_pick([i for i in items_b if i.get("unitOfMeasure") == uom_hr and _has_price(i)], uom_hr)
            if not row_b:
                row_b = _pick([i for i in items_b if _has_price(i)])
            unit_nat_hr = _d(row_b.get("retailPrice", 0)) if row_b else _d(0)

        total += unit_nat_hr * nat_cnt * nat_hours

        # Data processed
        if nat_gb > 0:
            ent_nat_gb = _ent_first(
                ent_prices,
                service_nat,
                ["Data Processed", "Data Processed (GB)", "Data Processing"],
                region,
                uom_gb,
            )

            if ent_nat_gb is not None:
                unit_nat_gb = ent_nat_gb
            else:
                flts_data = [
                    (f"serviceName eq 'NAT Gateway' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                     "and (contains(meterName,'Data Processed') or contains(productName,'Data Processed'))"),
                    ("serviceName eq 'NAT Gateway' and priceType eq 'Consumption' "
                     "and (contains(meterName,'Data Processed') or contains(productName,'Data Processed'))"),
                ]
                items_d = _dedup_merge([retail_fetch_items(f, currency) for f in flts_data])
                row_d = retail_pick([i for i in items_d if i.get("unitOfMeasure") == uom_gb and _has_price(i)], uom_gb)
                if not row_d:
                    row_d = _pick([i for i in items_d if _has_price(i)])
                unit_nat_gb = _d(row_d.get("retailPrice", 0)) if row_d else _d(0)

            total += unit_nat_gb * nat_gb

    return total, "Private Networking (PE + NAT)"