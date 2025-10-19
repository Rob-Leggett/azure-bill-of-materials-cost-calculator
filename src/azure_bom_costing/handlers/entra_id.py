# =====================================================================================
# Microsoft Entra External ID (MAU-based billing). Example component:
# {
#   "type": "entra_external_id",
#   "monthly_active_users": 30000,
#   "mfa_enabled_pct": 0.9,
#   "premium_features": true,
#   "unit_price_override": null,   # optional base AUD/MAU override
#   "mfa_unit_override": null,     # optional AUD/MAU override for MFA
#   "included_free_mau": 50000     # optional free MAU allowance (default 50k free)
# }
#
# Notes:
# • Models Microsoft Entra External ID (formerly Azure AD B2C External Identities) costs.
# • Pricing is based on Monthly Active Users (MAU) with optional MFA add-on charges.
# • Fields:
#     - `monthly_active_users`: total MAUs observed in the month.
#     - `mfa_enabled_pct`: fraction (0–1) of users requiring MFA (e.g., 0.9 for 90%).
#     - `premium_features`: flag to annotate use of Premium features (no math unless priced separately).
#     - `unit_price_override`: optional override for base MAU cost (AUD per user).
#     - `mfa_unit_override`: optional override for MFA add-on cost (AUD per user).
#     - `included_free_mau`: free MAU allowance count before base charges apply (default 50,000).
# • Billing Units:
#     - Base usage: “1 User” (per MAU beyond the free allowance)
#     - MFA usage: “1 User” (per MFA-enabled MAU; no free allowance by default)
# • Automatically queries Microsoft Entra/Azure AD price meters (retail API), with enterprise sheet overrides
#   if provided.
# • Use when modeling customer/partner identity systems (B2C/B2B) on Entra External ID.
# =====================================================================================
from decimal import Decimal
from typing import List, Dict, Optional

from ..helpers import _d, _per_count_from_text, _arm_region, _text_fields
from ..pricing_sources import retail_fetch_items
from ..types import Key

# ---------- Entra External ID (MAU) ----------
def _pick_entra_external_id_row(items: List[dict], want_mfa: bool = False) -> Optional[dict]:
    if not items:
        return None
    def score(i: dict) -> int:
        txt = _text_fields(i)
        s = 0
        # Strong product cues
        if ("external id" in txt or "external identities" in txt or "entra" in txt) and ("mau" in txt or "user" in txt):
            s += 8
        # MFA vs base
        if want_mfa and ("mfa" in txt or "multi-factor" in txt or "authentication method" in txt):
            s += 6
        if not want_mfa and not any(k in txt for k in ["mfa", "multi-factor"]):
            s += 2
        # Per-user UOM preference
        u = (i.get("unitOfMeasure","") or "").lower()
        if "user" in u or "1 user" in u or "per user" in txt:
            s += 2
        # Only positive priced rows
        if _d(i.get("retailPrice", 0)) > 0:
            s += 1
        else:
            s -= 50
        return s
    candidates = [i for i in items if _d(i.get("retailPrice", 0)) > 0]
    if not candidates:
        return None
    return sorted(candidates, key=score, reverse=True)[0]

def price_entra_external_id(component, region, currency, ent_prices: Dict[Key, Decimal]):
    """
    Billing model:
      - Base MAU: charged per user beyond a free allowance (default 50,000 MAU).
      - MFA add-on: charged per MFA-enabled MAU (no free allowance unless your contract states so).
    """
    mau_total = _d(component.get("monthly_active_users", 0))
    if mau_total <= 0:
        return _d(0), "Entra External ID (0 MAU)"

    mfa_pct = _d(component.get("mfa_enabled_pct", 0))
    premium  = bool(component.get("premium_features", False))
    base_override = component.get("unit_price_override")
    mfa_override  = component.get("mfa_unit_override")
    included_free = int(component.get("included_free_mau", 50000))

    # Compute billable MAU after free allowance
    billable_mau = max(mau_total - _d(included_free), _d(0))

    # If everything’s free and no MFA cost, short-circuit with an explanatory line
    if billable_mau == 0 and (mfa_pct <= 0 or mfa_override == 0):
        det = [f"base:{mau_total} (first {included_free} free) @ 0/MAU"]
        if mfa_pct > 0:
            det.append("mfa:0 (no priced row or overridden 0)")
        if premium:
            det.append("(premium)")
        return _d(0), "Entra External ID " + " ".join(det)

    # Enterprise pricing first (base & MFA) — these are uncommon but supported
    # Note: Enterprise SKUs vary; we fall back to retail reliably.
    service_aliases = ["Azure Active Directory", "Microsoft Entra ID", "Microsoft Entra External ID"]
    arm_region = _arm_region(region)

    # If overrides are provided, use those and skip catalog
    if base_override is not None and (mfa_pct <= 0 or mfa_override is not None):
        base_unit = _d(base_override)
        total = base_unit * billable_mau
        details = [f"base:{billable_mau} (of {mau_total}; {included_free} free) @ {base_unit}/MAU"]
        if mfa_pct > 0:
            mfa_unit = _d(mfa_override or 0)
            total += mfa_unit * (mau_total * mfa_pct)
            details.append(f"mfa:{int(mfa_pct*100)}% @ {mfa_unit}/MAU")
        if premium:
            details.append("(premium)")
        return total, "Entra External ID " + " ".join(details)

    # Otherwise query Retail API broadly (regioned + global; service name variants)
    filters: List[str] = []
    for svc in service_aliases:
        filters.append(f"serviceName eq '{svc}' and armRegionName eq '{arm_region}' and priceType eq 'Consumption'")
        filters.append(f"serviceName eq '{svc}' and priceType eq 'Consumption'")

    items: List[dict] = []
    seen = set()
    for f in filters:
        try:
            chunk = retail_fetch_items(f, currency)
            for it in chunk:
                key = it.get("meterId") or (it.get("productId"), it.get("skuId"), it.get("meterName"))
                if key not in seen:
                    seen.add(key)
                    items.append(it)
        except Exception:
            pass

    # Base MAU price (per user)
    if base_override is not None:
        base_unit = _d(base_override)
    else:
        row_base = _pick_entra_external_id_row(items, want_mfa=False)
        base_unit = _d(row_base.get("retailPrice", 0)) if row_base else _d(0)
        per = _per_count_from_text(row_base.get("unitOfMeasure","") if row_base else "", row_base or {})
        if per and per > 0 and per != 1:
            base_unit = base_unit / per

    total = base_unit * billable_mau
    details = [f"base:{billable_mau} (of {mau_total}; {included_free} free) @ {base_unit}/MAU"]

    # MFA add-on (per MFA-enabled MAU, no free allowance by default)
    if mfa_pct > 0:
        if mfa_override is not None:
            mfa_unit = _d(mfa_override)
        else:
            row_mfa = _pick_entra_external_id_row(items, want_mfa=True)
            mfa_unit = _d(row_mfa.get("retailPrice", 0)) if row_mfa else _d(0)
            per = _per_count_from_text(row_mfa.get("unitOfMeasure","") if row_mfa else "", row_mfa or {})
            if per and per > 0 and per != 1:
                mfa_unit = mfa_unit / per
        total += mfa_unit * (mau_total * mfa_pct)
        details.append(f"mfa:{int(mfa_pct*100)}% @ {mfa_unit}/MAU")

    if premium:
        details.append("(premium)")

    return total, "Entra External ID " + " ".join(details)