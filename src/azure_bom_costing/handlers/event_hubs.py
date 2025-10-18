# =====================================================================================
# Event Hubs (Throughput Units) / Service Bus / Event Grid
# =====================================================================================
from decimal import Decimal
from typing import Dict

from ..helpers import _d, _pick, _arm_region
from ..pricing_sources import enterprise_lookup, retail_fetch_items, retail_pick
from ..types import Key


def price_event_hub(component, region, currency, ent_prices: Dict[Key, Decimal]):
    tier = component.get("tier", "Standard")
    tu = _d(component.get("throughput_units", 1))
    hours = _d(component.get("hours_per_month", 730))
    service, uom = "Event Hubs", "1 Hour"
    sku = f"{tier} Throughput Unit"
    ent = enterprise_lookup(ent_prices, service, sku, region, uom)
    if ent is None:
        arm = _arm_region(region)
        items = retail_fetch_items(
            f"serviceName eq 'Event Hubs' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
            f"and (contains(meterName,'Throughput') or contains(skuName,'{tier}'))",
            currency
        )
        row = _pick(items, uom)
        unit = _d(row.get("retailPrice", 0)) if row else _d(0)
    else:
        unit = ent
    return unit * tu * hours, f"Event Hubs {tier} TU @ {unit}/hr × {tu} × {hours}h"

def price_service_bus(component, region, currency, ent_prices: Dict[Key, Decimal]):
    tier = component.get("tier", "Premium")  # Premium billed by Messaging Units
    mu = _d(component.get("messaging_units", 1))
    hours = _d(component.get("hours_per_month", 730))
    service, uom = "Service Bus", "1 Hour"
    sku = f"{tier} Messaging Unit"
    ent = enterprise_lookup(ent_prices, service, sku, region, uom)
    if ent is None:
        arm = _arm_region(region)
        items = retail_fetch_items(
            f"serviceName eq 'Service Bus' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
            f"and (contains(meterName,'Messaging Unit') or contains(skuName,'{tier}'))",
            currency
        )
        row = _pick(items, uom)
        unit = _d(row.get("retailPrice", 0)) if row else _d(0)
    else:
        unit = ent
    return unit * mu * hours, f"Service Bus {tier} MU @ {unit}/hr × {mu} × {hours}h"

def price_event_grid(component, region, currency, ent_prices: Dict[Key, Decimal]):
    ops = _d(component.get("operations_per_month", 0))
    if ops <= 0:
        return _d(0), "Event Grid (0 ops)"
    service, uom = "Event Grid", "1,000,000"  # priced per million ops
    sku = "Operations"
    ent = enterprise_lookup(ent_prices, service, sku, region, uom)
    if ent is None:
        items = retail_fetch_items(
            "serviceName eq 'Event Grid' and priceType eq 'Consumption' "
            "and (contains(meterName,'Operations') or contains(productName,'Operations'))",
            currency
        )
        row = retail_pick(items, uom) or _pick(items)
        unit_per_million = _d(row.get("retailPrice", 0)) if row else _d(0)
    else:
        unit_per_million = ent
    return unit_per_million * (ops / _d(1_000_000)), f"Event Grid {ops} ops @ {unit_per_million}/1M"