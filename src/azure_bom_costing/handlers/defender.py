# =========================================================
# Microsoft Defender for Cloud (very simplified)
# component: { "type":"defender", "plan":"Servers", "resource_count": 20, "hours_per_month":730 }
# =========================================================
from decimal import Decimal
from typing import Dict

from ..helpers import _d, _arm_region, _pick
from ..pricing_sources import enterprise_lookup, retail_fetch_items
from ..types import Key


def price_defender(component, region, currency, ent_prices: Dict[Key, Decimal]):
    plan = (component.get("plan") or "Servers").title()
    count = _d(component.get("resource_count", 0))
    hours = _d(component.get("hours_per_month", 730))
    if count <= 0:
        return _d(0), "Defender (0 resources)"

    service, uom = "Microsoft Defender for Cloud", "1 Hour"
    sku = f"{plan}"
    ent = enterprise_lookup(ent_prices, service, sku, region, uom)
    if ent is None:
        arm = _arm_region(region)
        flt = (f"serviceName eq 'Microsoft Defender for Cloud' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
               f"and (contains(meterName,'{plan}') or contains(productName,'{plan}'))")
        row = _pick(retail_fetch_items(flt, currency), uom)
        unit = _d(row.get("retailPrice", 0)) if row else _d(0)
    else:
        unit = ent

    return unit * count * hours, f"Defender {plan} {count}x @ {unit}/hr × {hours}h"