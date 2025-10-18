# =========================================================
# Private Networking: Private Endpoints + NAT Gateway
# component:
#   { "type":"private_networking",
#     "private_endpoints": 6, "pe_hours": 730,
#     "nat_gateways": 2, "nat_hours": 730, "nat_data_gb": 1500 }
# =========================================================
from decimal import Decimal
from typing import Dict

from ..helpers import _d, _pick, _arm_region
from ..pricing_sources import retail_fetch_items, retail_pick
from ..types import Key


def price_private_networking(component, region, currency, ent_prices: Dict[Key, Decimal]):
    arm = _arm_region(region)
    total = _d(0)

    pe_cnt = _d(component.get("private_endpoints", 0))
    pe_hours = _d(component.get("pe_hours", 730))
    if pe_cnt > 0:
        # Private Endpoint per hour
        items = retail_fetch_items(
            f"serviceName eq 'Private Link' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
            "and (contains(meterName,'Private Endpoint') or contains(productName,'Private Endpoint'))", currency)
        row = retail_pick(items, "1 Hour") or _pick(items)
        unit_pe_hr = _d(row.get("retailPrice", 0)) if row else _d(0)
        total += unit_pe_hr * pe_cnt * pe_hours

    nat_cnt = _d(component.get("nat_gateways", 0))
    nat_hours = _d(component.get("nat_hours", 730))
    nat_gb = _d(component.get("nat_data_gb", 0))
    if nat_cnt > 0:
        # NAT Gateway per hour
        items = retail_fetch_items(
            f"serviceName eq 'NAT Gateway' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
            "and contains(meterName,'Gateway Hours')", currency)
        row = retail_pick(items, "1 Hour") or _pick(items)
        unit_nat_hr = _d(row.get("retailPrice", 0)) if row else _d(0)
        total += unit_nat_hr * nat_cnt * nat_hours

        # Data processed per GB
        if nat_gb > 0:
            items2 = retail_fetch_items(
                f"serviceName eq 'NAT Gateway' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                "and contains(meterName,'Data Processed')", currency)
            row2 = retail_pick(items2, "1 GB") or _pick(items2)
            unit_nat_gb = _d(row2.get("retailPrice", 0)) if row2 else _d(0)
            total += unit_nat_gb * nat_gb

    return total, "Private Networking (PE + NAT)"