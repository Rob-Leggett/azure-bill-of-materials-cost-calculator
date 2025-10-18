# =========================================================
# DNS + Traffic Manager
# component:
#   { "type":"dns_tm", "dns_zones": 5, "dns_queries_millions": 30,
#     "tm_profiles": 2, "tm_queries_millions": 20, "hours_per_month":730 }
# =========================================================
from decimal import Decimal
from typing import Dict

from ..helpers import _d, _pick, _arm_region
from ..pricing_sources import retail_fetch_items, retail_pick
from ..types import Key


def price_dns_tm(component, region, currency, ent_prices: Dict[Key, Decimal]):
    zones = _d(component.get("dns_zones", 0))
    dns_m = _d(component.get("dns_queries_millions", 0))
    tm_prof = _d(component.get("tm_profiles", 0))
    tm_m = _d(component.get("tm_queries_millions", 0))
    hours = _d(component.get("hours_per_month", 730))
    arm = _arm_region(region)
    total = _d(0)

    # DNS zones per month
    if zones > 0:
        service, uom = "DNS", "1/Month"
        items = retail_fetch_items(
            "serviceName eq 'DNS' and priceType eq 'Consumption' and contains(meterName,'Hosted Zone')",
            currency
        )
        row = retail_pick(items, uom) or _pick(items)
        unit_zone = _d(row.get("retailPrice", 0)) if row else _d(0)
        total += unit_zone * zones

    # DNS queries per 1M
    if dns_m > 0:
        items = retail_fetch_items(
            "serviceName eq 'DNS' and priceType eq 'Consumption' and contains(meterName,'DNS Queries')",
            currency
        )
        row = retail_pick(items, "1,000,000") or _pick(items)
        unit_per_m = _d(row.get("retailPrice", 0)) if row else _d(0)
        total += unit_per_m * dns_m

    # Traffic Manager profiles per hour
    if tm_prof > 0:
        service, uom = "Traffic Manager", "1 Hour"
        items = retail_fetch_items(
            f"serviceName eq 'Traffic Manager' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
            "and contains(meterName,'Profile')", currency)
        row = _pick(items, uom)
        unit_prof_hr = _d(row.get("retailPrice", 0)) if row else _d(0)
        total += unit_prof_hr * tm_prof * hours

    # Traffic Manager DNS queries per 1M
    if tm_m > 0:
        items = retail_fetch_items(
            "serviceName eq 'Traffic Manager' and priceType eq 'Consumption' and contains(meterName,'DNS Queries')",
            currency
        )
        row = retail_pick(items, "1,000,000") or _pick(items)
        unit_tm_m = _d(row.get("retailPrice", 0)) if row else _d(0)
        total += unit_tm_m * tm_m

    return total, "DNS + Traffic Manager"