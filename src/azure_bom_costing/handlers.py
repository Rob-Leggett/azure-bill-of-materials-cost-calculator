# src/azure_bom_costing/handlers.py
from __future__ import annotations
from typing import Dict, Tuple, Optional, List
from decimal import Decimal
import re  # <-- needed by _per_count_from_text

from .pricing_sources import (
    d, enterprise_lookup, retail_fetch_items, retail_pick
)

Key = Tuple[str, str, str, str]  # (serviceName, skuName, region, unitOfMeasure)

# ---------- Helpers ----------
def _arm_region(region_str: str) -> str:
    # "Australia East" -> "australiaeast"
    return region_str.strip().lower().replace(" ", "")

def _text_fields(i: dict) -> str:
    """Lower-cased concatenation of common descriptive fields."""
    return " ".join([
        (i.get("productName") or ""),
        (i.get("skuName") or ""),
        (i.get("meterName") or ""),
        (i.get("armSkuName") or ""),
    ]).lower()

def _pick_row_prefer_1h(items: List[dict], prefer_uom: str = "1 Hour") -> Optional[dict]:
    if not items:
        return None
    for i in items:
        if i.get("unitOfMeasure") == prefer_uom and d(i.get("retailPrice", 0)) > 0:
            return i
    for i in items:
        if d(i.get("retailPrice", 0)) > 0:
            return i
    return items[0]

def _per_count_from_text(uom: str, item: dict) -> Decimal:
    """
    Detect batch size like 10,000 / 100,000 even when the API doesn't put it in unitOfMeasure.
    Looks in unitOfMeasure and in meter/product/sku text; understands '10k', '100k', 'per 10k', etc.
    """
    s = (uom or "").lower().replace(",", "")
    txt = " ".join([
        item.get("meterName",""), item.get("productName",""), item.get("skuName","")
    ]).lower().replace(",", "")

    def detect(t: str) -> Optional[int]:
        if "100000" in t or "100k" in t: return 100000
        if "10000"  in t or "10k"  in t: return 10000
        if "1000"   in t or "1k"   in t: return 1000
        m = re.search(r"per\s+(\d+)\s*(k)?", t)  # e.g. "per 10k"
        if m:
            n = int(m.group(1))
            if m.group(2):  # "k"
                n *= 1000
            return n
        return None

    n = detect(s) or detect(txt)
    return d(n or 1)

# ----- VM helpers -----
def _pick_vm_item(items: List[dict], os_filter: str, prefer_uom: str = "1 Hour") -> Optional[dict]:
    """Prefer 1 Hour meters; try to match OS label across meterName, productName, skuName; fallback gracefully."""
    if not items:
        return None

    os_lower = os_filter.lower()

    def has_os(i: dict) -> bool:
        return any(os_lower in (i.get(k, "") or "").lower()
                   for k in ("meterName", "productName", "skuName"))

    # 1) 1 Hour + OS
    for i in items:
        if i.get("unitOfMeasure") == prefer_uom and has_os(i) and d(i.get("retailPrice", 0)) > 0:
            return i
    # 2) Any UOM + OS
    for i in items:
        if has_os(i) and d(i.get("retailPrice", 0)) > 0:
            return i
    # 3) 1 Hour, any OS
    for i in items:
        if i.get("unitOfMeasure") == prefer_uom and d(i.get("retailPrice", 0)) > 0:
            return i
    # 4) First positive price
    for i in items:
        if d(i.get("retailPrice", 0)) > 0:
            return i
    return items[0] if items else None

def _fallback_vm_items(sku: str, arm_region: str, currency: str) -> List[dict]:
    """Try broader VM queries if the strict SKU filter yields nothing."""
    filt = (
        "serviceName eq 'Virtual Machines' "
        f"and armRegionName eq '{arm_region}' "
        "and priceType eq 'Consumption'"
    )
    items = retail_fetch_items(filt, currency)
    if not items:
        return []
    sku_l = sku.lower()
    narrowed = [
        i for i in items
        if sku_l in (i.get("armSkuName","") or "").lower()
           or sku_l in (i.get("skuName","") or "").lower()
           or sku_l in (i.get("productName","") or "").lower()
           or sku_l in (i.get("meterName","") or "").lower()
    ]
    return narrowed or items

# ----- Storage helpers -----
def _pick_storage_capacity(items: List[dict], tier: str, redundancy: str) -> Optional[dict]:
    """
    From a broad 'Storage' + region + 'Data Stored' set, pick the best match for tier & redundancy.
    Preference order:
      1) unitOfMeasure == '1 GB/Month' + BOTH tier & redundancy tokens present
      2) '1 GB/Month' + tier present
      3) any UOM + BOTH tokens
      4) any row with a positive price
    """
    if not items:
        return None

    tier_l = tier.lower()     # 'hot' | 'cool' | 'archive'
    red_l  = redundancy.lower()  # 'lrs' | 'grs' | 'zrs' | 'ragrs' | 'gzrs' | 'ragzrs' (etc.)

    def norm(s: str) -> str:
        return s.lower().replace("-", "")

    red_l = norm(red_l)

    def both_tokens(text: str) -> bool:
        t = text
        return (tier_l in t) and (red_l in norm(t))

    def has_tier(text: str) -> bool:
        return tier_l in text

    # (1) 1GB/Month + BOTH tokens
    for i in items:
        if i.get("unitOfMeasure") == "1 GB/Month":
            txt = _text_fields(i)
            if both_tokens(txt) and d(i.get("retailPrice", 0)) > 0:
                return i

    # (2) 1GB/Month + TIER token
    for i in items:
        if i.get("unitOfMeasure") == "1 GB/Month":
            txt = _text_fields(i)
            if has_tier(txt) and d(i.get("retailPrice", 0)) > 0:
                return i

    # (3) Any UOM + BOTH tokens
    for i in items:
        txt = _text_fields(i)
        if both_tokens(txt) and d(i.get("retailPrice", 0)) > 0:
            return i

    # (4) Fallback: first positive price
    for i in items:
        if d(i.get("retailPrice", 0)) > 0:
            return i

    return None

# ----- App Service helpers -----
def _appsvc_tier_hint(sku: str) -> Optional[str]:
    """Rough productName tier hint from SKU (for broader fallbacks)."""
    s = sku.lower()
    if "v3" in s:
        return "Premium v3"
    if s.startswith("p"):
        return "Premium"
    if s.startswith("s"):
        return "Standard"
    if s.startswith("b"):
        return "Basic"
    return None

def _pick_app_service(items: List[dict], arm_region: str, prefer_uom: str = "1 Hour") -> Optional[dict]:
    """Prefer items with matching region and 1 Hour UOM; then relax."""
    if not items:
        return None

    # 1) Region + 1 Hour
    for i in items:
        if i.get("armRegionName") == arm_region and i.get("unitOfMeasure") == prefer_uom and d(i.get("retailPrice", 0)) > 0:
            return i
    # 2) Region any UOM
    for i in items:
        if i.get("armRegionName") == arm_region and d(i.get("retailPrice", 0)) > 0:
            return i
    # 3) Any region + 1 Hour
    for i in items:
        if i.get("unitOfMeasure") == prefer_uom and d(i.get("retailPrice", 0)) > 0:
            return i
    # 4) Any positive
    for i in items:
        if d(i.get("retailPrice", 0)) > 0:
            return i
    return items[0]

# ----- Bandwidth helpers -----
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

# ---------- Virtual Machines ----------
def price_vm(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = "Virtual Machines"
    sku = component["armSku"]  # e.g. "Standard_D4s_v5"
    os_filter = "Linux" if component.get("os", "").lower().startswith("lin") else "Windows"
    uom = "1 Hour"

    ent = enterprise_lookup(ent_prices, service, sku, region, uom)
    if ent is None:
        arm_region = _arm_region(region)
        filt = (
            "serviceName eq 'Virtual Machines' "
            f"and armSkuName eq '{sku}' "
            f"and armRegionName eq '{arm_region}' "
            "and priceType eq 'Consumption'"
        )
        items = retail_fetch_items(filt, currency)
        if not items:
            items = _fallback_vm_items(sku, arm_region, currency)
        row = _pick_vm_item(items, os_filter, uom)
        if not row:
            raise RuntimeError(f"No retail price for VM {sku} (region={arm_region})")
        unit = d(row.get("retailPrice", 0))
    else:
        unit = ent

    hours = d(component.get("hours_per_month", 730))
    count = d(component.get("count", 1))
    return unit * hours * count, f"VM {sku} x{count} @ {unit}/hr"

# ---------- App Service ----------
def price_app_service(component, region, currency, ent_prices: Dict[Key, Decimal]):
    service = "App Service"
    sku = component["sku"]              # e.g. "P1v3"
    uom = "1 Hour"

    ent = enterprise_lookup(ent_prices, service, sku, region, uom)
    if ent is None:
        arm_region = _arm_region(region)

        # Build a cascade of increasingly broad filters. We'll dedupe/merge results.
        filters: List[str] = [
            # Strict matches first
            ("serviceName eq 'App Service' "
             f"and skuName eq '{sku}' "
             f"and armRegionName eq '{arm_region}' "
             "and priceType eq 'Consumption'"),
            ("serviceName eq 'App Service' "
             f"and contains(skuName,'{sku}') "
             f"and armRegionName eq '{arm_region}' "
             "and priceType eq 'Consumption'"),

            # Same but without region (some rows omit armRegionName)
            ("serviceName eq 'App Service' "
             f"and skuName eq '{sku}' "
             "and priceType eq 'Consumption'"),
            ("serviceName eq 'App Service' "
             f"and contains(skuName,'{sku}') "
             "and priceType eq 'Consumption'"),

            # Match by productName carrying the tier words
            ("serviceName eq 'App Service' "
             "and contains(productName,'App Service') "
             f"and contains(productName,'{sku}') "
             "and priceType eq 'Consumption'"),
        ]

        hint = _appsvc_tier_hint(sku)  # e.g. "Premium v3" for P1v3
        if hint:
            filters += [
                ("serviceName eq 'App Service' "
                 f"and contains(productName,'{hint}') "
                 "and priceType eq 'Consumption'"),
                ("contains(productName,'App Service') "
                 f"and contains(productName,'{hint}') "
                 "and priceType eq 'Consumption'"),
            ]

        filters += [
            ("contains(productName,'App Service') "
             f"and contains(skuName,'{sku}') "
             "and priceType eq 'Consumption'"),
            ("serviceFamily eq 'Compute' "
             "and contains(productName,'App Service') "
             "and priceType eq 'Consumption'"),
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

        row = _pick_app_service(items, arm_region, uom)
        if not row:
            raise RuntimeError(f"No retail price for App Service {sku} (region={arm_region})")
        unit = d(row.get("retailPrice", 0))
    else:
        unit = ent

    hours = d(component.get("hours_per_month", 730))
    inst = d(component.get("instances", 1))
    return unit * hours * inst, f"AppService {sku} x{inst} @ {unit}/hr"

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

# ---------- Storage (Blob) ----------
def price_storage(component, region, currency, ent_prices: Dict[Key, Decimal]):
    sku = component["sku"]  # e.g., "Standard_LRS_Hot"
    tier = "Hot" if "Hot" in sku else ("Cool" if "Cool" in sku else ("Archive" if "Archive" in sku else "Hot"))
    # Accept broader redundancy flavours
    if   "RA-GZRS" in sku or "RAGZRS" in sku: redundancy = "RA-GZRS"
    elif "GZRS"   in sku:                      redundancy = "GZRS"
    elif "RA-GRS" in sku or "RAGRS" in sku:    redundancy = "RA-GRS"
    elif "ZRS"    in sku:                      redundancy = "ZRS"
    elif "GRS"    in sku:                      redundancy = "GRS"
    else:                                      redundancy = "LRS"

    tb = d(component.get("tb", 1))
    gb = tb * d(1024)

    service = "Storage"
    uom_cap = "1 GB/Month"

    ent_key_sku = f"{redundancy} {tier} Data Stored"
    ent = enterprise_lookup(ent_prices, service, ent_key_sku, region, uom_cap)
    if ent is None:
        arm_region = _arm_region(region)
        cap_filter = (
            "serviceName eq 'Storage' "
            f"and armRegionName eq '{arm_region}' "
            "and priceType eq 'Consumption' "
            "and contains(meterName,'Data Stored')"
        )
        cap_items = retail_fetch_items(cap_filter, currency)
        if not cap_items:
            cap_filter2 = (
                "serviceName eq 'Storage' "
                f"and armRegionName eq '{arm_region}' "
                "and priceType eq 'Consumption' "
                "and contains(productName,'Data Stored')"
            )
            cap_items = retail_fetch_items(cap_filter2, currency)

        cap_row = _pick_storage_capacity(cap_items, tier=tier, redundancy=redundancy)
        if not cap_row:
            raise RuntimeError(f"No capacity price for Storage {sku} (region={arm_region})")
        cap_unit = d(cap_row.get("retailPrice", 0))
    else:
        cap_unit = ent

    total = cap_unit * gb

    # Transactions (rough)
    tx = d(component.get("transactions_per_month", 0))
    if tx > 0:
        uom_tx_10k = "10,000"
        ent_tx = enterprise_lookup(ent_prices, service, f"{redundancy} {tier} Transactions", region, uom_tx_10k)
        if ent_tx is None:
            arm_region = _arm_region(region)
            tx_filter = (
                "serviceName eq 'Storage' "
                f"and armRegionName eq '{arm_region}' "
                "and priceType eq 'Consumption' "
                "and contains(meterName,'Transactions')"
            )
            tx_items = retail_fetch_items(tx_filter, currency)
            tx_row = retail_pick(tx_items) or (tx_items[0] if tx_items else None)
            if tx_row:
                unit = d(tx_row.get("retailPrice", 0))
                uom = (tx_row.get("unitOfMeasure", "") or "")
                per = _per_count_from_text(uom, tx_row)
                total += unit * (tx / per)
        else:
            total += ent_tx * (tx / d(10000))

    return total, f"Storage {sku} {tb}TB @ {cap_unit}/GB-mo (+tx)"

# ---------- Bandwidth / Egress ----------
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

# ---------- Microsoft Fabric capacity ----------
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
        items = [i for i in items if d(i.get("retailPrice", 0)) > 0]

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
        unit = d(row.get("retailPrice", 0))

    # Hours × days modeling
    hpd = d(component.get("hours_per_day", 24))
    dpm = d(component.get("days_per_month", 30))
    return unit * hpd * dpm, f"Fabric {sku} @ {unit}/hr × {hpd}h × {dpm}d"

# ---------- OneLake storage helper (reuses blob) ----------
def price_onelake_storage(component, region, currency, ent_prices: Dict[Key, Decimal]):
    total = d(0)
    details = []
    for label, tier in [("tb_hot", "Hot"), ("tb_cool", "Cool")]:
        tb = d(component.get(label, 0))
        if tb > 0:
            fake = {"sku": f"Standard_LRS_{tier}", "tb": float(tb)}
            part, _ = price_storage(fake, region, currency, ent_prices)
            total += part
            details.append(f"{tier}:{tb}TB")
    return total, f"OneLake {' '.join(details)}"