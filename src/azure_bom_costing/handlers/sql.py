# =====================================================================================
# Azure SQL Database (PaaS vCore Model). Example component:
# {
#   "type": "sql_paas",
#   "sku": "GP_S_Gen5_4",
#   "max_gb": 256,
#   "ha": true,
#   "hours_per_month": 730
# }
#
# Notes:
# • `sku` – SQL tier and configuration shorthand:
#     - Prefix: GP (General Purpose), BC (Business Critical), HS (Hyperscale)
#     - Mode: S (Serverless), P (Provisioned)
#     - Family: Gen5, Gen4, etc.
#     - Example: GP_S_Gen5_4 = General Purpose, Serverless, Gen5, 4 vCores
# • `max_gb` – Optional included storage size (adds per-GB-month pricing).
# • `ha` – High Availability flag; applies 1.5× multiplier if true.
# • `hours_per_month` – Runtime duration (default 730 hours for full-month uptime).
# • Prices are pulled from Enterprise Price Sheet (if present) or Retail API.
# • Billing unit: “1 Hour” per vCore; optional storage in “1 GB/Month”.
# =====================================================================================
from decimal import Decimal
from typing import List, Dict

from ..helpers import _d, _arm_region, _dedup_merge
from ..pricing_sources import enterprise_lookup, retail_fetch_items, retail_pick
from ..types import Key

# ---------- Azure SQL PaaS (vCore) ----------
def price_sql_paas(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = "Azure SQL Database"
    sku = component["sku"]                  # e.g., "GP_S_Gen5_4"
    uom = "1 Hour"

    # Parse shorthand like GP_S_Gen5_4
    def _parse_sql_sku(s: str):
        tier_map = {"GP": "General Purpose", "BC": "Business Critical", "HS": "Hyperscale"}
        mode_map = {"S": "Serverless", "P": "Provisioned"}
        parts = s.split("_")
        if len(parts) < 4:
            return (s, None, None, 1)
        tier = tier_map.get(parts[0], parts[0])
        mode = mode_map.get(parts[1], parts[1])
        family = parts[2]
        try:
            vcores = int(parts[3])
        except Exception:
            vcores = 1
        return (tier, mode, family, vcores)

    tier, mode, family, vcores = _parse_sql_sku(sku)
    hours = _d(component.get("hours_per_month", 730))

    # Enterprise price sheet first (exact key)
    ent = enterprise_lookup(ent_prices, service, sku, region, uom)
    if ent is not None:
        unit_vcore_hr = ent
        total = unit_vcore_hr * _d(vcores) * hours
        unit_txt = "enterprise_rate"
    else:
        arm_region = _arm_region(region)

        # Build robust filters, region-first → global; we will dedupe & then score.
        filters: List[str] = [
            # Regioned vCore rows
            ("serviceName eq 'Azure SQL Database' "
             f"and armRegionName eq '{arm_region}' "
             "and priceType eq 'Consumption' "
             "and (contains(meterName,'vCore') or contains(productName,'vCore'))"),

            # Regioned broad rows (some catalogs omit 'vCore' in meter)
            ("serviceName eq 'Azure SQL Database' "
             f"and armRegionName eq '{arm_region}' "
             "and priceType eq 'Consumption'"),

            # Global fallbacks
            ("serviceFamily eq 'Databases' "
             "and contains(productName,'SQL Database') "
             "and priceType eq 'Consumption'"),
            ("serviceName eq 'Azure SQL Database' "
             "and priceType eq 'Consumption'")
        ]

        batches = [retail_fetch_items(f, currency) for f in filters]
        items: List[dict] = _dedup_merge(batches)

        if not items:
            raise RuntimeError(f"No retail price rows found for SQL (region={arm_region})")

        # Filter out irrelevant SQL artifacts: DTU, Elastic Pools, Managed Instance, Reserved, Storage-only rows
        def bad_row(i: dict) -> bool:
            txt = " ".join([
                i.get("productName", ""),
                i.get("skuName", ""),
                i.get("meterName", "")
            ]).lower()
            bad = [
                "dtu", "elastic pool", "managed instance", "reserved capacity",
                "reserved vcore", "reserved", "hyperscale backup storage", "backup storage",
                "io", "i/o", "iops", "license", "software assurance"
            ]
            return any(b in txt for b in bad)

        items = [i for i in items if not bad_row(i) and _d(i.get("retailPrice", 0)) > 0]

        # Score candidates for the *compute vCore-hour* row
        t_l = (tier or "").lower()
        m_l = (mode or "").lower() if mode else ""
        f_l = (family or "").lower()

        def score(i: dict) -> int:
            text = " ".join([
                i.get("productName", ""), i.get("skuName", ""), i.get("meterName", "")
            ]).lower()
            s = 0
            if (i.get("armRegionName") or "").lower() == arm_region: s += 6
            if i.get("unitOfMeasure") == "1 Hour": s += 4
            if "vcore" in text: s += 5
            if "compute" in text: s += 3
            if t_l and t_l in text: s += 4     # general purpose, business critical, hyperscale
            if f_l and f_l in text: s += 3     # gen5, etc.
            if m_l and m_l in text: s += 2     # serverless, provisioned
            return s

        items.sort(key=score, reverse=True)
        top = next((i for i in items if score(i) > 0), None)
        if not top:
            raise RuntimeError(f"No retail compute vCore price for SQL {sku} (region={arm_region})")

        unit_vcore_hr = _d(top.get("retailPrice", 0))
        total = unit_vcore_hr * _d(vcores) * hours
        unit_txt = f"{unit_vcore_hr}"

    # Optional storage approximation (per GB-month)
    max_gb = _d(component.get("max_gb", 0))
    if max_gb > 0:
        s_service, s_sku, s_uom = "Azure SQL Database", "Data Stored", "1 GB/Month"
        s_ent = enterprise_lookup(ent_prices, s_service, s_sku, region, s_uom)
        if s_ent is not None:
            unit_storage = s_ent
        else:
            arm_region = _arm_region(region)
            filt_s = (
                "serviceName eq 'Azure SQL Database' "
                f"and armRegionName eq '{arm_region}' "
                "and priceType eq 'Consumption' "
                "and (contains(meterName,'Data Stored') or contains(productName,'Data Stored'))"
            )
            s_items = retail_fetch_items(filt_s, currency)
            s_row = retail_pick(s_items, s_uom) or (s_items[0] if s_items else None)
            unit_storage = _d(s_row.get("retailPrice", 0)) if s_row else _d(0)
        total += unit_storage * max_gb

    # Simple HA multiplier (approximate)
    if component.get("ha"):
        total *= _d("1.5")

    return total, f"SQL {sku} @ {unit_txt}/vCore-hr × {vcores} vC (+storage approx)"