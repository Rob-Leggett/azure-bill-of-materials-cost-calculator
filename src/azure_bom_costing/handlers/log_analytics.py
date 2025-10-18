from decimal import Decimal
from typing import List, Optional, Dict

from .common import _text_fields, _arm_region, _per_count_from_text
from ..pricing_sources import d, retail_fetch_items
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
        if d(i.get("retailPrice", 0)) <= 0:
            s -= 100
        return s

    candidates = [i for i in items if d(i.get("retailPrice", 0)) > 0]
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
    ingest_gb_per_day = d(component.get("ingest_gb_per_day", 0))
    retention_days = int(component.get("retention_days", 30))
    included_days = int(component.get("included_retention_days", 31))

    monthly_ingest_gb = ingest_gb_per_day * d(30)

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
        ingest_unit = d(ing_override)
    else:
        row_ing = _pick_log_analytics_row(items, "ingest")
        ingest_unit = d(row_ing.get("retailPrice", 0)) if row_ing else d(0)
        per = _per_count_from_text(row_ing.get("unitOfMeasure","") if row_ing else "", row_ing or {})
        if per != 1 and per > 0:
            ingest_unit = ingest_unit / per  # normalize to per GB

    # Retention price per GB-month (beyond included)
    extra_days = max(0, retention_days - included_days)
    if extra_days > 0:
        if ret_override is not None:
            retention_unit = d(ret_override)
        else:
            row_ret = _pick_log_analytics_row(items, "retention")
            retention_unit = d(row_ret.get("retailPrice", 0)) if row_ret else d(0)
            # already typically per GB/Month; normalize to per GB-month fraction later
        # chargeable GB-months ~= monthly_ingest_gb * (extra_days / 30)
        gb_months = monthly_ingest_gb * d(extra_days) / d(30)
        retention_cost = retention_unit * gb_months
    else:
        retention_unit = d(0)
        retention_cost = d(0)

    ingest_cost = ingest_unit * monthly_ingest_gb
    total = ingest_cost + retention_cost

    det = [
        f"ingest:{monthly_ingest_gb}GB @ {ingest_unit}/GB"
    ]
    if extra_days > 0:
        det.append(f"ret+{extra_days}d @ {retention_unit}/GB-mo")

    return total, "LogAnalytics " + " ".join(det)