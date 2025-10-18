# =========================================================
# Key Vault
# component:
#   { "type":"key_vault", "tier":"Standard|Premium", "operations": 500000, "hsm_keys": 5 }
# =========================================================
from decimal import Decimal
from typing import Dict

from ..helpers import _d, _arm_region, _pick
from ..pricing_sources import retail_fetch_items, retail_pick
from ..types import Key

def price_key_vault(component, region, currency, ent_prices: Dict[Key, Decimal]):
    tier = (component.get("tier") or "Standard").title()
    ops = _d(component.get("operations", 0))  # raw ops count
    hsm_keys = _d(component.get("hsm_keys", 0))
    arm = _arm_region(region)
    total = _d(0)

    # Operations per 10k
    if ops > 0:
        service, uom = "Key Vault", "10,000"
        items = retail_fetch_items(
            f"serviceName eq 'Key Vault' and priceType eq 'Consumption' "
            f"and (contains(meterName,'Operations') or contains(productName,'Operations'))", currency)
        row = retail_pick(items, uom) or _pick(items)
        unit_per_10k = _d(row.get("retailPrice", 0)) if row else _d(0)
        total += unit_per_10k * (ops / _d(10_000))

    # HSM Protected Keys per key/month (Premium only)
    if tier == "Premium" and hsm_keys > 0:
        items = retail_fetch_items(
            "serviceName eq 'Key Vault' and priceType eq 'Consumption' and contains(meterName,'HSM Protected Key')",
            currency
        )
        row = retail_pick(items, "1/Month") or _pick(items)
        unit_per_key = _d(row.get("retailPrice", 0)) if row else _d(0)
        total += unit_per_key * hsm_keys

    return total, f"Key Vault {tier} (ops+keys)"