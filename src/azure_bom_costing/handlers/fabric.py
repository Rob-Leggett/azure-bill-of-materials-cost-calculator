from decimal import Decimal
from typing import Dict, List

from .storage import price_blob_storage
from ..helpers import _d, _arm_region
from ..pricing_sources import retail_fetch_items, enterprise_lookup
from ..types import Key

# ---------- Fabric ----------
def price_fabric_capacity(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service, sku, uom = "Microsoft Fabric", component["sku"], "1 Hour"

    # 1) Enterprise first
    ent = enterprise_lookup(ent_prices, service, sku, region, uom)
    if ent is not None:
        unit = ent
    else:
        arm_region = _arm_region(region)

        # token variants commonly seen in catalogs
        tokens = {sku}
        if sku.upper().startswith("F") and sku[1:].isdigit():
            n = sku[1:]
            tokens.update({
                f"F{n}", f"F {n}", f"{sku} CU", f"Capacity {sku}", f"Capacity F{n}",
                f"{sku} Capacity", f"F{n} Capacity", f"F{n}CU"
            })

        svc_names = ["Microsoft Fabric", "Microsoft Fabric Capacity"]

        filters: List[str] = []

        # (a) strict service + region + sku-based
        for svc in svc_names:
            filters.append(
                f"serviceName eq '{svc}' and skuName eq '{sku}' "
                f"and armRegionName eq '{arm_region}' and priceType eq 'Consumption'"
            )
            filters.append(
                f"serviceName eq '{svc}' and contains(skuName,'{sku}') "
                f"and armRegionName eq '{arm_region}' and priceType eq 'Consumption'"
            )
            for t in tokens:
                filters.append(
                    f"serviceName eq '{svc}' and contains(productName,'{t}') "
                    f"and armRegionName eq '{arm_region}' and priceType eq 'Consumption'"
                )
                filters.append(
                    f"serviceName eq '{svc}' and contains(meterName,'{t}') "
                    f"and armRegionName eq '{arm_region}' and priceType eq 'Consumption'"
                )

        # (b) drop region (many Fabric rows omit armRegionName)
        for svc in svc_names:
            filters.append(
                f"serviceName eq '{svc}' and skuName eq '{sku}' and priceType eq 'Consumption'"
            )
            filters.append(
                f"serviceName eq '{svc}' and contains(skuName,'{sku}') and priceType eq 'Consumption'"
            )
            for t in tokens:
                filters.append(
                    f"serviceName eq '{svc}' and contains(productName,'{t}') and priceType eq 'Consumption'"
                )
                filters.append(
                    f"serviceName eq '{svc}' and contains(meterName,'{t}') and priceType eq 'Consumption'"
                )

        # (c) super-broad: no serviceName; must mention Fabric + token
        for t in tokens:
            filters.append(
                f"contains(productName,'Fabric') and contains(productName,'{t}') and priceType eq 'Consumption'"
            )
            filters.append(
                f"contains(meterName,'Fabric') and contains(meterName,'{t}') and priceType eq 'Consumption'"
            )

        # (d) last-ditch: just the token somewhere (some catalogs are messy)
        for t in tokens:
            filters.append(f"contains(skuName,'{t}') and priceType eq 'Consumption'")
            filters.append(f"contains(productName,'{t}') and priceType eq 'Consumption'")
            filters.append(f"contains(meterName,'{t}') and priceType eq 'Consumption'")

        # Execute & dedupe
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

        # Keep only positive-priced rows
        items = [i for i in items if _d(i.get("retailPrice", 0)) > 0]

        if not items:
            raise RuntimeError(f"No price found for Fabric {sku} (region={arm_region})")

        sku_l = sku.lower()
        token_l = {t.lower() for t in tokens}

        def score(i: dict) -> int:
            txt = " ".join([
                i.get("serviceName",""), i.get("productName",""),
                i.get("skuName",""), i.get("meterName","")
            ]).lower()
            s = 0
            if i.get("armRegionName") == arm_region: s += 6
            if i.get("unitOfMeasure") == uom: s += 4
            if "fabric" in txt: s += 3
            if any(t in txt for t in token_l): s += 5
            if sku_l in (i.get("skuName","") or "").lower(): s += 3
            if "capacity" in txt or "cu" in txt: s += 2
            return s

        items.sort(key=score, reverse=True)
        row = items[0]
        unit = _d(row.get("retailPrice", 0))

    # Hours × days modeling
    hpd = _d(component.get("hours_per_day", 24))
    dpm = _d(component.get("days_per_month", 30))
    return unit * hpd * dpm, f"Fabric {sku} @ {unit}/hr × {hpd}h × {dpm}d"

# ---------- OneLake storage helper (reuses blob) ----------
def price_onelake_storage(component, region, currency, ent_prices: Dict[Key, Decimal]):
    total = _d(0)
    details = []
    for label, tier in [("tb_hot", "Hot"), ("tb_cool", "Cool")]:
        tb = _d(component.get(label, 0))
        if tb > 0:
            fake = {"sku": f"Standard_LRS_{tier}", "tb": float(tb)}
            part, _ = price_blob_storage(fake, region, currency, ent_prices)
            total += part
            details.append(f"{tier}:{tb}TB")
    return total, f"OneLake {' '.join(details)}"