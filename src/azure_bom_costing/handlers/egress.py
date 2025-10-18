from decimal import Decimal
from typing import List, Optional, Dict

from .common import _arm_region
from ..pricing_sources import d, retail_fetch_items, enterprise_lookup
from ..types import Key

# ---------- Bandwidth / Egress ----------
def _egress_zone_for_region(region_display: str) -> Optional[str]:
    """Map ARM display region to Azure egress pricing zone label."""
    r = region_display.strip().lower()
    zone1 = {"east us", "west us", "central us", "north central us", "south central us",
             "west europe", "north europe", "france central", "uksouth", "uk south",
             "germany west central", "switzerland north", "norway east", "italy north",
             "canada central", "canada east"}
    zone2 = {"japan east", "japan west", "korea central", "korea south",
             "australia southeast", "australia se",
             "east asia", "southeast asia", "south india", "central india", "west india"}
    zone3 = {"australia east", "australiaeast", "new zealand north", "brazil south",
             "south africa north", "uae north", "qatar central", "poland central"}
    if r in zone1: return "Zone 1"
    if r in zone2: return "Zone 2"
    if r in zone3: return "Zone 3"
    if r.replace(" ", "") == "australiaeast": return "Zone 3"
    return None

def _pick_egress_item(items: List[dict], arm_region: str, zone_label: Optional[str], prefer_uom: str = "1 GB") -> Optional[dict]:
    """Pick a sensible *Internet* egress row (favor Zone; exclude non-Internet)."""
    if not items:
        return None
    z = (zone_label or "").lower()

    # Things we definitely do NOT want to price as Internet egress
    bad_tokens = [
        "peering", "to microsoft", "microsoft network", "private",
        "vpn", "expressroute", "front door", "cdn",
        "within region", "intra-zone", "inter-zone",
        "between regions", "data transfer in", "inbound"
    ]

    def score(i: dict) -> int:
        price = d(i.get("retailPrice", 0))
        if price <= 0:
            return -999

        txt = " ".join([
            i.get("serviceName",""), i.get("productName",""),
            i.get("skuName",""), i.get("meterName","")
        ]).lower()

        # Reject clearly non-Internet rows
        if any(b in txt for b in bad_tokens):
            return -500

        s = 0
        # Strong Internet/outbound signals
        if "internet" in txt: s += 30
        if "data transfer out" in txt or "outbound" in txt: s += 20

        # Prefer explicit Zone label when armRegionName is missing
        if z and z in txt: s += 15

        # Prefer exact region when present
        if (i.get("armRegionName") or "").lower() == arm_region: s += 6

        # Prefer correct UOM
        if (i.get("unitOfMeasure") or "") == prefer_uom: s += 4

        return s

    candidates = [i for i in items if d(i.get("retailPrice", 0)) > 0]
    if not candidates:
        return None
    candidates.sort(key=score, reverse=True)

    # Final sanity: if the top still smells like non-Internet, try the next best
    for c in candidates:
        txt = " ".join([c.get("productName",""), c.get("skuName",""), c.get("meterName","")]).lower()
        if not any(b in txt for b in bad_tokens):
            return c
    return candidates[0]

def price_bandwidth(component, region, currency, ent_prices: Dict[Key, Decimal]):
    gb = d(component.get("gb_per_month", 0))
    if gb <= 0:
        return d(0), "Bandwidth (none)"

    service, sku, uom = "Bandwidth", "Data Transfer Out", "1 GB"

    # Enterprise sheet (rare for egress, but try)
    ent = enterprise_lookup(ent_prices, service, sku, region, uom)
    if ent is not None:
        unit = ent
        picked_desc = "enterprise sheet"
    else:
        arm_region = _arm_region(region)
        zone_lbl   = _egress_zone_for_region(region)

        # Build filters; prefer Zone-labelled Internet egress first
        filters: List[str] = []
        if zone_lbl:
            z = zone_lbl
            filters += [
                ("serviceName eq 'Bandwidth' and priceType eq 'Consumption' "
                 f"and contains(productName,'Data Transfer Out') and contains(productName,'Internet') and contains(productName,'{z}')"),
                ("serviceName eq 'Bandwidth' and priceType eq 'Consumption' "
                 f"and contains(meterName,'Data Transfer Out') and contains(meterName,'Internet') and contains(productName,'{z}')"),
                ("serviceName eq 'Bandwidth' and priceType eq 'Consumption' "
                 f"and contains(productName,'Outbound') and contains(productName,'Internet') and contains(productName,'{z}')"),
            ]

        # Region-specific fallbacks
        filters += [
            ("serviceName eq 'Bandwidth' "
             f"and armRegionName eq '{arm_region}' "
             "and priceType eq 'Consumption' "
             "and (contains(productName,'Data Transfer Out') or contains(productName,'Outbound'))"),
            ("serviceName eq 'Bandwidth' "
             f"and armRegionName eq '{arm_region}' "
             "and priceType eq 'Consumption' "
             "and (contains(meterName,'Data Transfer Out') or contains(meterName,'Outbound'))"),
            ("serviceName eq 'Bandwidth' "
             f"and armRegionName eq '{arm_region}' "
             "and priceType eq 'Consumption'"),
            # Catalogs sometimes omit armRegionName for Internet egress; rely on wording
            ("serviceName eq 'Bandwidth' and priceType eq 'Consumption' "
             "and (contains(productName,'Data Transfer Out') or contains(productName,'Outbound'))"),
            ("serviceName eq 'Bandwidth' and priceType eq 'Consumption'")
        ]

        # Fetch & dedupe
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

        row = _pick_egress_item(items, arm_region, zone_lbl, uom)
        if not row:
            # Don’t crash overall costing if catalog is weird
            return d(0), "Egress (unpriced — no suitable catalog row found)"

        unit = d(row.get("retailPrice", 0))
        picked_desc = f"{row.get('productName','?')} / {row.get('meterName','?')}"

        # Guardrail: if we somehow grabbed a suspiciously-low non-Internet rate,
        # try to upgrade to an Internet+Zone row if available.
        if unit < d("0.03") and zone_lbl:
            zone_l = zone_lbl.lower()
            better = [
                i for i in items
                if d(i.get("retailPrice", 0)) > 0
                   and "internet" in " ".join([i.get("productName",""), i.get("meterName","")]).lower()
                   and zone_l in " ".join([i.get("productName",""), i.get("meterName","")]).lower()
            ]
            if better:
                better.sort(key=lambda j: d(j.get("retailPrice", 0)))
                unit2 = d(better[0].get("retailPrice", 0))
                if unit2 > unit:
                    unit = unit2
                    picked_desc = f"{better[0].get('productName','?')} / {better[0].get('meterName','?')}"

    total = unit * gb
    return total, f"Egress {gb}GB @ {unit}/GB ({picked_desc})"