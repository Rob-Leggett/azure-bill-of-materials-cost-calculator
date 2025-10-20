# =====================================================================================
# Azure Key Vault. Example component:
# {
#   "type": "key_vault",
#   "tier": "Standard|Premium",
#   "operations": 500000,
#   "hsm_keys": 5
# }
#
# Notes:
# • Models Azure Key Vault operational and HSM-key storage costs.
# • `tier` – "Standard" (software-protected) or "Premium" (HSM-protected keys).
# • `operations` – Number of vault operations per month (billed per 10,000 ops).
# • `hsm_keys` – Number of HSM-protected keys (billed per key per month, Premium only).
# • Billing units:
#     - Operations: “per 10,000 operations”
#     - HSM Protected Keys: “per key per month”
# • For Premium tier, adds key-based HSM charge on top of operation charges.
# • Automatically retrieves regional consumption rates from Azure Retail API.
# • Typical usage includes secrets, certificates, and key operations for app services.
# =====================================================================================
from decimal import Decimal
from typing import Dict, List, Optional

from ..helpers import _d, _arm_region, _pick, _per_count_from_text, _dedup_merge
from ..pricing_sources import retail_fetch_items, retail_pick, enterprise_lookup
from ..types import Key

def _ent_try(ent_prices: Dict[Key, Decimal], service: str, sku_candidates: List[str],
             region: str, uom_candidates: List[str]) -> Optional[Decimal]:
    """Try multiple likely SKU/UOM combos in enterprise sheet (with and without region)."""
    for sku in sku_candidates:
        for uom in uom_candidates:
            v = enterprise_lookup(ent_prices, service, sku, region, uom)
            if v is not None:
                return v
            v = enterprise_lookup(ent_prices, service, sku, "", uom)  # sheets sometimes omit region
            if v is not None:
                return v
    return None


def _first_positive(items: List[dict], want_uom: Optional[str] = None) -> Optional[dict]:
    """Pick first positive-price row, preferring a specific UOM if provided."""
    if not items:
        return None
    if want_uom:
        for i in items:
            if i.get("unitOfMeasure") == want_uom and _d(i.get("retailPrice", 0)) > 0:
                return i
    for i in items:
        if _d(i.get("retailPrice", 0)) > 0:
            return i
    return None


def price_key_vault(component, region, currency, ent_prices: Dict[Key, Decimal]):
    tier = (component.get("tier") or "Standard").title()  # "Standard" | "Premium"
    ops = _d(component.get("operations", 0))              # raw operation count per month
    hsm_keys = _d(component.get("hsm_keys", 0))
    arm = _arm_region(region)
    total = _d(0)
    detail_bits: List[str] = []

    # ---------- Operations (per 10k) ----------
    if ops > 0:
        svc = "Key Vault"
        uom_ops_default = "10,000"

        # Enterprise first — try a few SKU/UOM phrasings
        ent_ops = _ent_try(
            ent_prices,
            service=svc,
            sku_candidates=[
                "Operations", "Requests", f"{tier} Operations", f"{tier} Requests"
            ],
            region=region,
            uom_candidates=[uom_ops_default, "10000", "10K", "Per 10,000 Operations"]
        )
        if ent_ops is not None:
            unit_per_10k = ent_ops
        else:
            # Retail — regioned then global; accept common wording variants
            filters = [
                (f"serviceName eq 'Key Vault' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                 "and (contains(meterName,'Operations') or contains(meterName,'Requests') "
                 "or contains(productName,'Operations') or contains(productName,'Requests'))"),
                ("serviceName eq 'Key Vault' and priceType eq 'Consumption' "
                 "and (contains(meterName,'Operations') or contains(meterName,'Requests') "
                 "or contains(productName,'Operations') or contains(productName,'Requests'))"),
            ]
            items = _dedup_merge([retail_fetch_items(f, currency) for f in filters])
            row = retail_pick(items, uom_ops_default) or _first_positive(items, uom_ops_default) or _first_positive(items)
            if not row:
                # last-ditch: use any row we see
                row = _pick(items)
            unit = _d(row.get("retailPrice", 0)) if row else _d(0)

            # Normalize to per 10k operations if the catalog UOM is different
            per = _per_count_from_text((row.get("unitOfMeasure") or "") if row else "", row or {})
            if per and per != 10_000:
                unit_per_10k = unit * (_d(10_000) / _d(per))
            else:
                unit_per_10k = unit

        cost_ops = unit_per_10k * (ops / _d(10_000))
        total += cost_ops
        detail_bits.append(f"ops:{ops} @ {unit_per_10k}/10k")

    # ---------- HSM Protected Keys (per key / month) ----------
    if tier == "Premium" and hsm_keys > 0:
        svc = "Key Vault"
        uom_key = "1/Month"

        # Enterprise first — common SKU wordings
        ent_key = _ent_try(
            ent_prices,
            service=svc,
            sku_candidates=["HSM Protected Key", "HSM Key", "Premium HSM Protected Key"],
            region=region,
            uom_candidates=[uom_key, "1 Month", "Per Month"]
        )
        if ent_key is not None:
            unit_key = ent_key
        else:
            filters = [
                (f"serviceName eq 'Key Vault' and armRegionName eq '{arm}' and priceType eq 'Consumption' "
                 "and (contains(meterName,'HSM') and (contains(meterName,'Key') or contains(productName,'Key')))"),
                ("serviceName eq 'Key Vault' and priceType eq 'Consumption' "
                 "and (contains(meterName,'HSM') and (contains(meterName,'Key') or contains(productName,'Key')))"),
            ]
            items = _dedup_merge([retail_fetch_items(f, currency) for f in filters])
            row = retail_pick(items, uom_key) or _first_positive(items, uom_key) or _first_positive(items)
            unit_key = _d(row.get("retailPrice", 0)) if row else _d(0)
            # UOM here is typically per key per month; if it’s per N keys/month, normalize:
            per = _per_count_from_text((row.get("unitOfMeasure") or "") if row else "", row or {})
            if per and per != 1:
                unit_key = unit_key / _d(per)

        cost_keys = unit_key * hsm_keys
        total += cost_keys
        detail_bits.append(f"hsm:{hsm_keys} @ {unit_key}/key-mo")

    if not detail_bits:
        return _d(0), f"Key Vault {tier} (no usage)"

    return total, f"Key Vault {tier} ({', '.join(detail_bits)})"