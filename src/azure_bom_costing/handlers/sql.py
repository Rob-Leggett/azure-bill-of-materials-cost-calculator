from decimal import Decimal
from typing import List, Dict

from .common import _arm_region
from ..pricing_sources import enterprise_lookup, retail_fetch_items, retail_pick, d
from ..types import Key

# ---------- Azure SQL PaaS (vCore) ----------
def price_sql_paas(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = "Azure SQL Database"
    sku = component["sku"]  # e.g., "GP_S_Gen5_4"
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

    ent = enterprise_lookup(ent_prices, service, sku, region, uom)
    if ent is not None:
        hours = d(component.get("hours_per_month", 730))
        total = ent * d(vcores) * hours
        unit_txt = "enterprise_rate"
    else:
        arm_region = _arm_region(region)

        filters = [
            ("serviceName eq 'Azure SQL Database' "
             f"and armRegionName eq '{arm_region}' "
             "and priceType eq 'Consumption' "
             "and contains(meterName,'vCore')"),
            ("serviceName eq 'Azure SQL Database' "
             f"and armRegionName eq '{arm_region}' "
             "and priceType eq 'Consumption'"),
            ("serviceFamily eq 'Databases' "
             "and contains(productName,'SQL Database') "
             f"and armRegionName eq '{arm_region}' "
             "and priceType eq 'Consumption'"),
        ]

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

        if not items:
            raise RuntimeError(f"No retail price rows found for SQL (region={arm_region})")

        t_l = (tier or "").lower()
        m_l = (mode or "").lower() if mode else ""
        f_l = (family or "").lower()

        def score(i: dict) -> int:
            text = " ".join([
                i.get("productName", ""), i.get("skuName", ""), i.get("meterName", "")
            ]).lower()
            s = 0
            if "vcore" in text: s += 4
            if t_l and t_l in text: s += 4      # General Purpose / Business Critical / Hyperscale
            if f_l and f_l in text: s += 3      # Gen5, etc.
            if m_l and m_l in text: s += 2      # Serverless vs Provisioned
            if i.get("unitOfMeasure") == "1 Hour": s += 2
            if "compute" in text: s += 1
            return s

        items_scored = sorted(items, key=score, reverse=True)
        top = next((i for i in items_scored if score(i) > 0 and d(i.get("retailPrice", 0)) > 0), None)
        if not top:
            top = next((i for i in items_scored if d(i.get("retailPrice", 0)) > 0), None)
        if not top:
            raise RuntimeError(f"No retail price for SQL {sku} (region={arm_region})")

        unit_vcore_hr = d(top.get("retailPrice", 0))
        hours = d(component.get("hours_per_month", 730))
        total = unit_vcore_hr * d(vcores) * hours
        unit_txt = f"{unit_vcore_hr}"

    # Optional storage approximation
    max_gb = d(component.get("max_gb", 0))
    if max_gb > 0:
        s_service, s_sku, s_uom = "Azure SQL Database", "Data Stored", "1 GB/Month"
        s_ent = enterprise_lookup(ent_prices, s_service, s_sku, region, s_uom)
        if s_ent is None:
            arm_region = _arm_region(region)
            filt_s = (
                "serviceName eq 'Azure SQL Database' "
                "and contains(productName,'Data Stored') "
                f"and armRegionName eq '{arm_region}' "
                "and priceType eq 'Consumption'"
            )
            s_items = retail_fetch_items(filt_s, currency)
            s_row = retail_pick(s_items, s_uom) or (s_items[0] if s_items else None)
            if s_row:
                total += d(s_row.get("retailPrice", 0)) * max_gb
        else:
            total += s_ent * max_gb

    if component.get("ha"):
        total *= d("1.5")

    return total, f"SQL {sku} @ {unit_txt}/vCore-hr × {vcores} vC (+storage approx)"