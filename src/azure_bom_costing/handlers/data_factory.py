# =====================================================================================
# Data Factory (very simplified: DIU hours + pipeline runs)
# component: { "type":"data_factory", "diu_hours": 200, "activity_runs_1k": 50 }
# =====================================================================================
from decimal import Decimal
from typing import Dict

from ..helpers import _d, _pick, _arm_region
from ..pricing_sources import enterprise_lookup, retail_fetch_items, retail_pick
from ..types import Key


def price_data_factory(component, region, currency, ent_prices: Dict[Key, Decimal]):
    arm = _arm_region(region)
    diu_hours = _d(component.get("diu_hours", 0))
    runs_1k  = _d(component.get("activity_runs_1k", 0))

    total = _d(0)

    # DIU hours
    if diu_hours > 0:
        service, uom = "Data Factory", "1 Hour"
        ent = enterprise_lookup(ent_prices, service, "Data Movement", region, uom)
        if ent is not None:
            unit = ent
        else:
            filters = [
                (f"serviceName eq 'Data Factory' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                 "and (contains(meterName,'DIU') or contains(productName,'Data Movement'))"),
                ("serviceName eq 'Data Factory' and priceType eq 'Consumption' and contains(meterName,'DIU')"),
            ]
            it = []
            for f in filters: it += retail_fetch_items(f, currency)
            row = _pick(it, uom)
            unit = _d(row.get("retailPrice", 0)) if row else _d(0)
        total += unit * diu_hours

    # Pipeline activity per 1k
    if runs_1k > 0:
        service, uom = "Data Factory", "1,000"
        ent = enterprise_lookup(ent_prices, service, "Pipeline Activities", region, uom)
        if ent is not None:
            unit = ent
        else:
            filters = [
                (f"serviceName eq 'Data Factory' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                 "and (contains(meterName,'Pipeline') or contains(productName,'Pipeline')))"),
                ("serviceName eq 'Data Factory' and priceType eq 'Consumption' and contains(meterName,'Pipeline')"),
            ]
            it = []
            for f in filters: it += retail_fetch_items(f, currency)
            row = retail_pick(it, uom) or _pick(it)
            unit = _d(row.get("retailPrice", 0)) if row else _d(0)
        total += unit * runs_1k

    return total, f"Data Factory (DIU:{diu_hours}h, Activities:{runs_1k}k)"