# =====================================================================================
# Load Balancer / Application Gateway (v2)
# =====================================================================================
from decimal import Decimal
from typing import Dict

from ..helpers import _d, _pick, _arm_region
from ..pricing_sources import retail_fetch_items, enterprise_lookup
from ..types import Key


def price_load_balancer(component, region, currency, ent_prices: Dict[Key, Decimal]):
    sku = component.get("sku", "Standard")
    data_gb = _d(component.get("data_processed_gb", 0))
    rules   = _d(component.get("rules", 0))
    hours   = _d(component.get("hours_per_month", 730))
    arm = _arm_region(region)
    total = _d(0)

    # Data processed (GB)
    if data_gb > 0:
        service, uom = "Load Balancer", "1 GB"
        ent = enterprise_lookup(ent_prices, service, f"{sku} Data Processed", region, uom)
        if ent is None:
            items = retail_fetch_items(
                f"serviceName eq 'Load Balancer' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                f"and contains(meterName,'Data Processed')",
                currency
            )
            row = _pick(items, uom)
            unit = _d(row.get("retailPrice", 0)) if row else _d(0)
        else:
            unit = ent
        total += unit * data_gb

    # Rule hours (approx: some SKUs have per-rule-hour)
    if rules > 0:
        service, uom = "Load Balancer", "1 Hour"
        items = retail_fetch_items(
            f"serviceName eq 'Load Balancer' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
            f"and (contains(meterName,'Rule') or contains(productName,'Rule'))",
            currency
        )
        row = _pick(items, uom)
        unit = _d(row.get("retailPrice", 0)) if row else _d(0)
        total += unit * rules * hours

    return total, f"Load Balancer {sku} (data:{data_gb}GB, rules:{rules} × {hours}h)"

def price_app_gateway(component, region, currency, ent_prices: Dict[Key, Decimal]):
    # v2: capacity units + data processed GB
    cap_units = _d(component.get("capacity_units", 0))
    data_gb   = _d(component.get("data_processed_gb", 0))
    hours     = _d(component.get("hours_per_month", 730))
    arm = _arm_region(region)
    total = _d(0)

    # Capacity Unit per hour
    if cap_units > 0:
        service, uom = "Application Gateway", "1 Hour"
        items = retail_fetch_items(
            f"serviceName eq 'Application Gateway' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
            "and contains(meterName,'Capacity Unit')",
            currency
        )
        row = _pick(items, uom)
        cu_unit = _d(row.get("retailPrice", 0)) if row else _d(0)
        total += cu_unit * cap_units * hours

    # Data processed GB
    if data_gb > 0:
        service, uom = "Application Gateway", "1 GB"
        items = retail_fetch_items(
            f"serviceName eq 'Application Gateway' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
            "and contains(meterName,'Data Processed')",
            currency
        )
        row = _pick(items, uom)
        dp_unit = _d(row.get("retailPrice", 0)) if row else _d(0)
        total += dp_unit * data_gb

    return total, f"App Gateway v2 (CU:{cap_units} × {hours}h, data:{data_gb}GB)"