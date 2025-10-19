# =====================================================================================
# Azure Application Insights (telemetry ingestion + data retention). Example component:
# {
#   "type": "app_insights",
#   "ingest_gb_per_day": 10,
#   "retention_days": 30
# }
#
# Notes:
# • Models Application Insights data ingestion and retention costs.
# • Typically used to separate App Insights telemetry from Log Analytics line items.
# • Pricing based on daily data volume and retention duration.
#
# • Core parameters:
#     - `ingest_gb_per_day` → Average daily ingestion volume in GB
#     - `retention_days` → Total retention period in days
#     - `included_retention_days` → Optional number of days included in base plan (default 0)
#     - `days_per_month` → Used to scale daily ingestion (default 30)
#
# • Pricing structure:
#     - serviceName eq 'Application Insights'
#     - meterName contains 'Data Ingested' → unitOfMeasure = "1 GB"
#     - meterName contains 'Data Retention' → unitOfMeasure = "1 GB/Month"
#
# • Enterprise lookup supported:
#     enterprise_lookup(ent_prices, "Application Insights", "Data Ingested", region, "1 GB")
#     enterprise_lookup(ent_prices, "Application Insights", "Data Retention", region, "1 GB/Month")
# • Retail fallback queries Azure Retail Prices API if enterprise sheet unavailable.
#
# • Calculation:
#     ingestion_cost = ingest_gb_per_day × days_per_month × rate_per_GB_ingested
#     retention_cost = rate_per_GB_month × (billable_days / 30) × (ingest_gb_per_day × days_per_month)
#     total_cost = ingestion_cost + retention_cost
#
# • Example output:
#     App Insights ingest:10GB/d @ 0.0036/GB + retention 30d = $1.08/month
#
# • Typical uses:
#     - Telemetry collection for applications using Application Insights
#     - Cost transparency for ingestion vs retention beyond included quota
# • Commonly paired with Log Analytics (for correlated query/alerting) but costed separately here.
# =====================================================================================
from decimal import Decimal
from typing import Dict

from ..helpers import _d
from ..pricing_sources import enterprise_lookup, retail_fetch_items, retail_pick
from ..types import Key


def price_app_insights(component, region, currency, ent_prices: Dict[Key, Decimal]):
    ingest_gb_day = _d(component.get("ingest_gb_per_day", 0))
    retention_days = int(component.get("retention_days", 30))
    days = _d(component.get("days_per_month", 30))

    # Ingestion GB (per GB)
    service_ing, uom_ing = "Application Insights", "1 GB"
    ent_ing = enterprise_lookup(ent_prices, service_ing, "Data Ingested", region, uom_ing)
    if ent_ing is not None:
        unit_ing = ent_ing
    else:
        flt = ("serviceName eq 'Application Insights' and priceType eq 'Consumption' "
               "and (contains(meterName,'Data Ingested') or contains(productName,'Data Ingested'))")
        row = retail_pick(retail_fetch_items(flt, currency), uom_ing)
        unit_ing = _d(row.get("retailPrice", 0)) if row else _d(0)

    ingest_total = unit_ing * ingest_gb_day * days

    # Retention beyond included (simplified: charge for all retention_days)
    # Some offers include 90 days; adjust if you prefer.
    included = int(component.get("included_retention_days", 0))
    billable_days = max(retention_days - included, 0)
    retention_total = _d(0)
    if billable_days > 0:
        service_ret, uom_ret = "Application Insights", "1 GB/Month"
        ent_ret = enterprise_lookup(ent_prices, service_ret, "Data Retention", region, uom_ret)
        if ent_ret is not None:
            unit_ret = ent_ret
        else:
            flt2 = ("serviceName eq 'Application Insights' and priceType eq 'Consumption' "
                    "and (contains(meterName,'Data Retention') or contains(productName,'Data Retention'))")
            row2 = retail_pick(retail_fetch_items(flt2, currency), uom_ret)
            unit_ret = _d(row2.get("retailPrice", 0)) if row2 else _d(0)
        # Approximate: pro-rate per day against 30-day month
        gb_month = ingest_gb_day * days
        retention_total = unit_ret * gb_month * _d(billable_days) / _d(30)

    total = ingest_total + retention_total
    return total, f"App Insights ingest:{ingest_gb_day}GB/d @ {unit_ing}/GB + retention {billable_days}d"