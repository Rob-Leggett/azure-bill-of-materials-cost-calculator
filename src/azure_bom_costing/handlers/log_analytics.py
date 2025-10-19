# =====================================================================================
# Azure Log Analytics (Data Ingestion + Retention). Example component:
# {
#   "type": "log_analytics",
#   "ingest_gb_per_day": 50,
#   "retention_days": 30,          # Total retention (hot data)
#   "included_retention_days": 31, # Default included retention
#   "unit_price_override": null,   # Optional per-GB ingest override
#   "retention_price_override": null  # Optional per-GB-month override
# }
#
# Notes:
# • Models Azure Monitor / Log Analytics workspace costs for ingestion and retention.
# • `ingest_gb_per_day` – Daily data volume ingested into Log Analytics (in GB).
# • `retention_days` – Total data retention period in days (default 30).
# • `included_retention_days` – Days of hot data retention included for free (default 31).
# • `unit_price_override` – Optional manual override for ingest price per GB.
# • `retention_price_override` – Optional manual override for retention price per GB-month.
# • Billing units:
#     - Ingestion: “per GB”
#     - Retention: “per GB-month” (charged only for days beyond included retention)
# • Total charge = Ingest cost + Retention cost (if retention_days > included_days)
# • Useful for Observability, Security, and Application Insights backend logs.
# • Automatically fetches regional or global Log Analytics rates from Azure Retail API.
# =====================================================================================
from decimal import Decimal
from typing import List, Optional, Dict

from ..helpers import _d, _text_fields, _arm_region, _per_count_from_text
from ..pricing_sources import retail_fetch_items
from ..types import Key

# ---------- Log Analytics ----------
def _pick_log_analytics_row(items: List[dict], kind: str) -> Optional[dict]:
    """
    kind: 'ingest' or 'retention'
    """
    if not items:
        return None
    k = kind.lower()

    def score(i: dict) -> int:
        txt = _text_fields(i)
        s = 0
        if "log analytics" in txt or "azure monitor" in txt:
            s += 3
        if k == "ingest" and ("ingest" in txt or "data ingestion" in txt or "per gb" in txt):
            s += 6
        if k == "retention" and ("retention" in txt or "data retention" in txt):
            s += 6
        if "1 gb" in (i.get("unitOfMeasure","") or "").lower():
            s += 2
        if _d(i.get("retailPrice", 0)) <= 0:
            s -= 100
        return s

    candidates = [i for i in items if _d(i.get("retailPrice", 0)) > 0]
    if not candidates:
        return None
    return sorted(candidates, key=score, reverse=True)[0]

def price_log_analytics(component, region, currency, ent_prices: Dict[Key, Decimal]):
    """
    component schema (suggested):
      {
        "type": "log_analytics",
        "ingest_gb_per_day": 50,
        "retention_days": 30,         # total hot retention
        "unit_price_override": null,  # optional per-GB ingest override
        "retention_price_override": null,  # optional per-GB-month override
        "included_retention_days": 31
      }
    """
    ingest_gb_per_day = _d(component.get("ingest_gb_per_day", 0))
    retention_days = int(component.get("retention_days", 30))
    included_days = int(component.get("included_retention_days", 31))

    monthly_ingest_gb = ingest_gb_per_day * _d(30)

    # Enterprise lookup is uncommon here; skip and go straight to retail (overrides win)
    ing_override = component.get("unit_price_override")
    ret_override = component.get("retention_price_override")

    arm_region = _arm_region(region)

    # Gather catalog rows
    filters: List[str] = []
    for svc in ["Log Analytics", "Azure Monitor"]:
        # regioned
        filters.append(f"serviceName eq '{svc}' and armRegionName eq '{arm_region}' and priceType eq 'Consumption'")
        # global
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

    # Ingestion price per GB
    if ing_override is not None:
        ingest_unit = _d(ing_override)
    else:
        row_ing = _pick_log_analytics_row(items, "ingest")
        ingest_unit = _d(row_ing.get("retailPrice", 0)) if row_ing else _d(0)
        per = _per_count_from_text(row_ing.get("unitOfMeasure","") if row_ing else "", row_ing or {})
        if per != 1 and per > 0:
            ingest_unit = ingest_unit / per  # normalize to per GB

    # Retention price per GB-month (beyond included)
    extra_days = max(0, retention_days - included_days)
    if extra_days > 0:
        if ret_override is not None:
            retention_unit = _d(ret_override)
        else:
            row_ret = _pick_log_analytics_row(items, "retention")
            retention_unit = _d(row_ret.get("retailPrice", 0)) if row_ret else _d(0)
            # already typically per GB/Month; normalize to per GB-month fraction later
        # chargeable GB-months ~= monthly_ingest_gb * (extra_days / 30)
        gb_months = monthly_ingest_gb * _d(extra_days) / _d(30)
        retention_cost = retention_unit * gb_months
    else:
        retention_unit = _d(0)
        retention_cost = _d(0)

    ingest_cost = ingest_unit * monthly_ingest_gb
    total = ingest_cost + retention_cost

    det = [
        f"ingest:{monthly_ingest_gb}GB @ {ingest_unit}/GB"
    ]
    if extra_days > 0:
        det.append(f"ret+{extra_days}d @ {retention_unit}/GB-mo")

    return total, "LogAnalytics " + " ".join(det)