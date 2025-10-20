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
from typing import List, Dict, Optional, Tuple

from ..helpers import _d, _per_count_from_text, _arm_region, _text_fields
from ..pricing_sources import retail_fetch_items
from ..types import Key

# ---------- Entra External ID (MAU) ----------
_SERVICE_ALIASES = ["Microsoft Entra External ID", "Microsoft Entra ID", "Azure Active Directory"]

def _ent_pick_user_price(
        ent_prices: Dict[Key, Decimal],
        region: str,
        want_mfa: bool = False,
) -> Optional[Tuple[Decimal, str]]:
    """
    Try to find an enterprise-sheet per-user price.
    We scan the ent_prices dict tolerantly because sheets vary in 'ServiceName'/'SkuName' wording.
    Returns (unit_price_per_user, debug_text) or None.
    """
    if not ent_prices:
        return None

    svc_alias_l = [s.lower() for s in _SERVICE_ALIASES]
    region_l = (region or "").lower()

    # Tokens to look for in SKU/Meter text
    base_tokens = ["external id", "external identities", "mau", "user", "external"]
    mfa_tokens  = ["mfa", "multi-factor", "multi factor", "authentication method"]

    best: Optional[Tuple[Decimal, int, str]] = None  # (price, score, debug)

    for (svc, sku, rgn, uom), price in ent_prices.items():
        # service match (tolerant)
        svc_l = (svc or "").lower()
        if not any(a in svc_l for a in svc_alias_l):
            continue

        # region must match or be blank in sheet
        if rgn and rgn.lower() not in (region_l, ):
            continue

        # we want per-user like units
        uom_l = (uom or "").lower()
        if not any(k in uom_l for k in ["user", "1 user", "per user"]):
            continue

        # score by token match
        txt = f"{sku} {uom}".lower()
        score = 0
        toks = (mfa_tokens if want_mfa else base_tokens)
        for t in toks:
            if t in txt: score += 3

        # De-prioritize MFA rows when want_mfa=False, and vice versa
        if want_mfa and any(t in txt for t in base_tokens):
            score -= 1
        if (not want_mfa) and any(t in txt for t in mfa_tokens):
            score -= 2

        # prefer explicit 'mau' or 'user'
        if "mau" in txt or "user" in txt: score += 1

        if score <= 0:
            continue

        try:
            px = _d(price)
        except Exception:
            continue

        if px <= 0:
            continue

        if best is None or score > best[1] or (score == best[1] and px < best[0]):
            best = (px, score, f"svc='{svc}', sku='{sku}', uom='{uom}', rgn='{rgn or '∅'}'")

    if best:
        return Decimal(best[0]), best[2]
    return None

def _pick_entra_external_id_row(items: List[dict], want_mfa: bool = False) -> Optional[dict]:
    if not items:
        return None
    def score(i: dict) -> int:
        txt = _text_fields(i)
        s = 0
        if ("external id" in txt or "external identities" in txt or "entra" in txt) and ("mau" in txt or "user" in txt):
            s += 8
        if want_mfa and ("mfa" in txt or "multi-factor" in txt or "authentication method" in txt):
            s += 6
        if not want_mfa and not any(k in txt for k in ["mfa", "multi-factor"]):
            s += 2
        u = (i.get("unitOfMeasure","") or "").lower()
        if "user" in u or "1 user" in u or "per user" in txt:
            s += 2
        if _d(i.get("retailPrice", 0)) <= 0:
            s -= 100
        return s
    cands = [i for i in items if _d(i.get("retailPrice", 0)) > 0]
    if not cands:
        return None
    return sorted(cands, key=score, reverse=True)[0]

# ---------- main ----------
def price_entra_external_id(component, region, currency, ent_prices: Dict[Key, Decimal]):
    """
    Billing:
      - Base MAU: per user beyond free allowance (default 50,000 free).
      - MFA add-on: per MFA-enabled user (no free allowance).
    """
    mau_total = _d(component.get("monthly_active_users", 0))
    if mau_total <= 0:
        return _d(0), "Entra External ID (0 MAU)"

    mfa_pct       = _d(component.get("mfa_enabled_pct", 0))
    premium       = bool(component.get("premium_features", False))
    base_override = component.get("unit_price_override")
    mfa_override  = component.get("mfa_unit_override")
    included_free = int(component.get("included_free_mau", 50000))

    billable_mau = max(mau_total - _d(included_free), _d(0))
    arm_region = _arm_region(region)

    # --------- Overrides short-circuit ----------
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

    # --------- Enterprise sheet (tolerant scan) ----------
    ent_base = _ent_pick_user_price(ent_prices, region, want_mfa=False)
    ent_mfa  = _ent_pick_user_price(ent_prices, region, want_mfa=True)

    # --------- If enterprise covers base (and possibly MFA), use it; otherwise fall back to retail ----------
    details: List[str] = []
    total = _d(0)

    # Base price per user (enterprise → override → retail)
    if ent_base:
        base_unit = _d(ent_base[0])
        details_src = "ent"
    elif base_override is not None:
        base_unit = _d(base_override)
        details_src = "override"
    else:
        # Retail fetch (regioned + global across service aliases)
        filters: List[str] = []
        for svc in _SERVICE_ALIASES:
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
        row_base = _pick_entra_external_id_row(items, want_mfa=False)
        base_unit = _d(row_base.get("retailPrice", 0)) if row_base else _d(0)
        per = _per_count_from_text(row_base.get("unitOfMeasure","") if row_base else "", row_base or {})
        if per and per > 0 and per != 1:
            base_unit = base_unit / per
        details_src = "retail"

    total += base_unit * billable_mau
    details.append(f"base:{billable_mau} (of {mau_total}; {included_free} free) @ {base_unit}/MAU[{details_src}]")

    # MFA price (enterprise → override → retail)
    if mfa_pct > 0:
        if ent_mfa:
            mfa_unit = _d(ent_mfa[0])
            mfa_src = "ent"
        elif mfa_override is not None:
            mfa_unit = _d(mfa_override)
            mfa_src = "override"
        else:
            # reuse the items (retail) if we fetched above, else fetch now
            if 'items' not in locals():
                filters = []
                for svc in _SERVICE_ALIASES:
                    filters.append(f"serviceName eq '{svc}' and armRegionName eq '{arm_region}' and priceType eq 'Consumption'")
                    filters.append(f"serviceName eq '{svc}' and priceType eq 'Consumption'")
                items = []
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
            row_mfa = _pick_entra_external_id_row(items, want_mfa=True)
            mfa_unit = _d(row_mfa.get("retailPrice", 0)) if row_mfa else _d(0)
            per = _per_count_from_text(row_mfa.get("unitOfMeasure","") if row_mfa else "", row_mfa or {})
            if per and per > 0 and per != 1:
                mfa_unit = mfa_unit / per
            mfa_src = "retail"

        total += mfa_unit * (mau_total * mfa_pct)
        details.append(f"mfa:{int(mfa_pct*100)}% @ {mfa_unit}/MAU[{mfa_src}]")

    if premium:
        details.append("(premium)")

    return total, "Entra External ID " + " ".join(details)