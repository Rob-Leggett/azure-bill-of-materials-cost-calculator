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
from typing import List, Optional, Dict, Tuple

from ..helpers import _d, _text_fields, _arm_region, _per_count_from_text
from ..pricing_sources import retail_fetch_items, enterprise_lookup
from ..types import Key

# ---------- Log Analytics ----------
_SVC_CANDIDATES = ["Log Analytics", "Azure Monitor", "Azure Monitor Logs"]

def _ent_lookup_many(ent_prices: Dict[Key, Decimal],
                     services: List[str],
                     sku_candidates: List[str],
                     region: str,
                     uom_candidates: List[str]) -> Optional[Tuple[Decimal, str, str]]:
    """Try multiple (service, sku, uom) combos; return (price, sku, uom) on first hit."""
    for svc in services:
        for sku in sku_candidates:
            for uom in uom_candidates:
                ent = enterprise_lookup(ent_prices, svc, sku, region, uom)
                if ent is not None:
                    return ent, sku, uom
                # some sheets omit region:
                ent = enterprise_lookup(ent_prices, svc, sku, "", uom)
                if ent is not None:
                    return ent, sku, uom
    return None

def _norm_unit(unit_price: Decimal, uom: str, fallback_per: int) -> Decimal:
    """
    Normalize a unit price to 'per 1 GB' (fallback_per=1) or 'per 1 GB-month' (fallback_per=1),
    depending on caller’s intent. If the UOM implies 'per 10 GB' etc., scale accordingly.
    """
    per = _per_count_from_text(uom or "", {}) or _d(fallback_per)
    if per <= 0:
        per = _d(fallback_per)
    return unit_price / per

def _pick_log_analytics_row(items: List[dict], kind: str) -> Optional[dict]:
    """Retail scoring: prefer rows that look like ingest or retention, with positive price."""
    if not items:
        return None
    k = (kind or "").lower()

    def score(i: dict) -> int:
        txt = _text_fields(i)
        s = 0
        if "log analytics" in txt or "azure monitor" in txt:
            s += 3
        if k == "ingest" and ("ingest" in txt or "data ingestion" in txt or "gb ingested" in txt or "per gb" in txt):
            s += 8
        if k == "retention" and ("retention" in txt or "data retention" in txt or "per gb-month" in txt):
            s += 8
        # prefer clear UOMs
        u = (i.get("unitOfMeasure","") or "").lower()
        if k == "ingest" and "1 gb" in u:
            s += 2
        if k == "retention" and ("gb/month" in u or "gb-mo" in u):
            s += 2
        # positive price only
        if _d(i.get("retailPrice", 0)) <= 0:
            s -= 100
        return s

    rows = [i for i in items if _d(i.get("retailPrice", 0)) > 0]
    if not rows:
        return None
    rows.sort(key=score, reverse=True)
    return rows[0]


# ---------- main ----------

def price_log_analytics(component, region, currency, ent_prices: Dict[Key, Decimal]):
    """
    {
      "type": "log_analytics",
      "ingest_gb_per_day": 50,
      "retention_days": 30,
      "included_retention_days": 31,
      "unit_price_override": null,        # per GB ingest
      "retention_price_override": null    # per GB-month retention
    }
    """
    ingest_gb_per_day = _d(component.get("ingest_gb_per_day", 0))
    retention_days = int(component.get("retention_days", 30))
    included_days = int(component.get("included_retention_days", 31))

    monthly_ingest_gb = ingest_gb_per_day * _d(30)
    extra_days = max(0, retention_days - included_days)

    # Optional overrides win
    ing_override = component.get("unit_price_override")
    ret_override = component.get("retention_price_override")

    arm_region = _arm_region(region)

    # ------- Enterprise first: try to match common sheet wordings -------
    ingest_ent = None
    retention_ent = None

    ingest_skus = [
        "Data Ingestion", "Ingestion", "GB Ingested", "Log Data Ingestion",
        "Log Analytics Data Ingestion", "Data Processed"
    ]
    retention_skus = [
        "Data Retention", "Retention", "GB Retention", "Log Data Retention",
        "Log Analytics Data Retention"
    ]
    ingest_uoms = ["1 GB", "GB", "GB/Month", "1 GB/Month"]   # sheets differ; we normalize below
    retention_uoms = ["1 GB/Month", "GB/Month", "1 GB per Month"]

    hit = _ent_lookup_many(ent_prices, _SVC_CANDIDATES, ingest_skus, region, ingest_uoms)
    if hit:
        price, sku, uom = hit
        # normalize to per 1 GB
        ingest_ent = _norm_unit(price, uom, fallback_per=1)

    hit = _ent_lookup_many(ent_prices, _SVC_CANDIDATES, retention_skus, region, retention_uoms)
    if hit:
        price, sku, uom = hit
        # normalize to per 1 GB-month
        retention_ent = _norm_unit(price, uom, fallback_per=1)

    # ------- Retail fallback (if no overrides / enterprise match) -------
    filters: List[str] = []
    for svc in ["Log Analytics", "Azure Monitor"]:
        filters.append(f"serviceName eq '{svc}' and armRegionName eq '{arm_region}' and priceType eq 'Consumption'")
        filters.append(f"serviceName eq '{svc}' and priceType eq 'Consumption'")  # many rows are global

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

    # Ingestion per GB
    if ing_override is not None:
        ingest_unit = _d(ing_override)
    elif ingest_ent is not None:
        ingest_unit = _d(ingest_ent)
    else:
        row_ing = _pick_log_analytics_row(items, "ingest")
        ingest_unit = _d(row_ing.get("retailPrice", 0)) if row_ing else _d(0)
        # normalize to per GB if needed
        ingest_unit = _norm_unit(ingest_unit, row_ing.get("unitOfMeasure","") if row_ing else "", fallback_per=1)

    # Retention per GB-month (only charged beyond included retention)
    if extra_days > 0:
        if ret_override is not None:
            retention_unit = _d(ret_override)
        elif retention_ent is not None:
            retention_unit = _d(retention_ent)
        else:
            row_ret = _pick_log_analytics_row(items, "retention")
            retention_unit = _d(row_ret.get("retailPrice", 0)) if row_ret else _d(0)
            # normalize to per GB-month if needed (kept as 1 GB-month baseline)
            retention_unit = _norm_unit(retention_unit, row_ret.get("unitOfMeasure","") if row_ret else "", fallback_per=1)
        gb_months = monthly_ingest_gb * _d(extra_days) / _d(30)
        retention_cost = retention_unit * gb_months
    else:
        retention_unit = _d(0)
        retention_cost = _d(0)

    ingest_cost = ingest_unit * monthly_ingest_gb
    total = ingest_cost + retention_cost

    det = [f"ingest:{monthly_ingest_gb}GB @ {ingest_unit}/GB"]
    if extra_days > 0:
        det.append(f"ret+{extra_days}d @ {retention_unit}/GB-mo")

    return total, "LogAnalytics " + " ".join(det)