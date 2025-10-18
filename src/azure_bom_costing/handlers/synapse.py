# =====================================================================================
# Synapse Dedicated SQL Pool (DWU). Example component:
# { "type":"synapse_sqlpool", "sku":"DW1000c", "hours_per_month": 200 }
# =====================================================================================
from decimal import Decimal
from typing import List, Dict

from ..helpers import _d, _arm_region, _pick
from ..pricing_sources import enterprise_lookup, retail_fetch_items
from ..types import Key

def _parse_dwu(sku: str) -> int:
    # DW100c, DW1000c, DW30000c etc.
    s = sku.lower().replace("dw","").replace("c","")
    try:
        return int(s)
    except Exception:
        return 100

def price_synapse_sqlpool(component, region, currency, ent_prices: Dict[Key, Decimal]):
    sku = component.get("sku", "DW100c")
    dwu = _parse_dwu(sku)
    hours = _d(component.get("hours_per_month", 730))
    service, uom = "Azure Synapse Analytics", "1 Hour"

    # Try enterprise
    ent = enterprise_lookup(ent_prices, service, sku, region, uom)
    if ent is not None:
        unit_per_dwu = ent  # assume per-DWU-hour
    else:
        arm = _arm_region(region)
        filters = [
            (f"serviceName eq 'Azure Synapse Analytics' and armRegionName eq '{arm}' "
             "and priceType eq 'Consumption' and (contains(meterName,'DWU') or contains(productName,'Dedicated SQL'))"),
            ("serviceName eq 'Azure Synapse Analytics' and priceType eq 'Consumption' "
             "and (contains(meterName,'DWU') or contains(productName,'Dedicated SQL') or contains(productName,'SQL Data Warehouse'))"),
        ]
        items: List[dict] = []
        for f in filters:
            items += retail_fetch_items(f, currency)
        row = _pick(items, uom)
        if not row:
            return _d(0), f"Synapse SQLPool {sku} (unpriced)"
        unit_per_dwu = _d(row.get("retailPrice", 0))

    total = unit_per_dwu * _d(dwu) * hours
    return total, f"Synapse SQLPool {sku} @ {unit_per_dwu}/DWU-hr × {dwu} DWU × {hours}h"