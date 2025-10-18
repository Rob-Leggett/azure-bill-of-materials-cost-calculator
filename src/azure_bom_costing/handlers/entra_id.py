from decimal import Decimal
from typing import List, Dict, Optional

from .common import _per_count_from_text, _arm_region, _text_fields
from ..pricing_sources import d, retail_fetch_items
from ..types import Key

# ---------- Entra External ID (MAU) ----------
def _pick_entra_external_id_row(items: List[dict], want_mfa: bool = False) -> Optional[dict]:
    if not items:
        return None

    def score(i: dict) -> int:
        txt = _text_fields(i)
        s = 0
        if ("external id" in txt or "external identities" in txt or "entra" in txt) and ("mau" in txt or "user" in txt):
            s += 8
        if want_mfa and ("mfa" in txt or "multi-factor" in txt):
            s += 6
        if not want_mfa and not any(k in txt for k in ["mfa", "multi-factor"]):
            s += 2
        if "per user" in txt or "1 user" in (i.get("unitOfMeasure","") or "").lower():
            s += 2
        if d(i.get("retailPrice", 0)) > 0:
            s += 1
        else:
            s -= 50
        return s

    items = [i for i in items if d(i.get("retailPrice", 0)) > 0]
    if not items:
        return None
    return sorted(items, key=score, reverse=True)[0]


def price_entra_external_id(component, region, currency, ent_prices: Dict[Key, Decimal]):
    """
    component schema (suggested):
      {
        "type": "entra_external_id",
        "monthly_active_users": 30000,
        "mfa_enabled_pct": 0.9,
        "premium_features": true,
        "unit_price_override": null,     # optional AUD/MAU override
        "mfa_unit_override": null        # optional AUD/MAU override for MFA
      }
    """
    mau = d(component.get("monthly_active_users", 0))
    if mau <= 0:
        return d(0), "Entra External ID (0 MAU)"

    mfa_pct = d(component.get("mfa_enabled_pct", 0))
    premium  = bool(component.get("premium_features", False))
    base_override = component.get("unit_price_override")
    mfa_override  = component.get("mfa_unit_override")

    service_names = [
        "Azure Active Directory", "Microsoft Entra ID", "Microsoft Entra External ID"
    ]
    arm_region = _arm_region(region)

    if base_override is not None and (mfa_pct <= 0 or mfa_override is not None):
        # All prices provided — no retail lookup needed
        base_unit = d(base_override)
        total = base_unit * mau
        details = [f"base:{mau} @ {base_unit}/MAU"]
        if mfa_pct > 0:
            mfa_unit = d(mfa_override or 0)
            total += mfa_unit * (mau * mfa_pct)
            details.append(f"mfa:{int(mfa_pct*100)}% @ {mfa_unit}/MAU")
        return total, "Entra External ID " + " ".join(details)

    # Otherwise try catalog
    filters: List[str] = []
    for svc in service_names:
        # regioned then global
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

    # Base MAU price
    if base_override is not None:
        base_unit = d(base_override)
    else:
        row_base = _pick_entra_external_id_row(items, want_mfa=False)
        base_unit = d(row_base.get("retailPrice", 0)) if row_base else d(0)
        # normalize to per user if needed
        per = _per_count_from_text(row_base.get("unitOfMeasure","") if row_base else "", row_base or {})
        if per != 1 and per > 0:
            base_unit = base_unit / per

    total = base_unit * mau
    details = [f"base:{mau} @ {base_unit}/MAU"]

    # MFA add-on
    if mfa_pct > 0:
        if mfa_override is not None:
            mfa_unit = d(mfa_override)
        else:
            row_mfa = _pick_entra_external_id_row(items, want_mfa=True)
            mfa_unit = d(row_mfa.get("retailPrice", 0)) if row_mfa else d(0)
            per = _per_count_from_text(row_mfa.get("unitOfMeasure","") if row_mfa else "", row_mfa or {})
            if per != 1 and per > 0:
                mfa_unit = mfa_unit / per
        total += mfa_unit * (mau * mfa_pct)
        details.append(f"mfa:{int(mfa_pct*100)}% @ {mfa_unit}/MAU")

    # Premium feature note (no extra math unless you set overrides or catalog has a distinct SKU)
    if premium:
        details.append("(premium)")

    return total, "Entra External ID " + " ".join(details)