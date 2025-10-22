from __future__ import annotations
from decimal import Decimal
from typing import List, Dict, Any, Optional

from ..helpers.csv import clean_rows
from ..helpers.http import http_get_json, http_get
from ..helpers.math import decimal
from ..types import Key

import csv

# ---------- Download Enterprise price sheet (MCA / EA) ----------
def download_price_sheet_mca(access_token: str, billing_account_id: str) -> List[Dict[str, Any]] | dict:
    url = (
        "https://management.azure.com/providers/Microsoft.Billing/"
        f"billingAccounts/{billing_account_id}/providers/Microsoft.CostManagement/"
        "pricesheets/default/download?api-version=2023-03-01"
    )
    headers = {"Authorization": f"Bearer {access_token}"}
    meta = http_get_json(url, headers=headers)
    download_url = meta.get("properties", {}).get("downloadUrl")
    if not download_url:
        raise RuntimeError("Failed to obtain downloadUrl for MCA price sheet")

    resp = http_get(download_url)
    content_type = resp.headers.get("Content-Type", "").lower()
    if "csv" in content_type or download_url.lower().endswith(".csv"):
        text = resp.content.decode("utf-8", errors="ignore")
        rows = list(csv.DictReader(text.splitlines()))
        return clean_rows(rows)
    # Some tenants respond with JSON (rare); best-effort clean if it is a list of dicts
    data = http_get_json(download_url)
    if isinstance(data, list) and all(isinstance(x, dict) for x in data):
        return clean_rows(data)  # best-effort mapping
    return data  # unknown JSON shape; let caller decide

def download_price_sheet_ea(access_token: str, enrollment_account_id: str) -> List[Dict[str, Any]] | dict:
    url = (
        "https://management.azure.com/providers/Microsoft.Billing/"
        f"enrollmentAccounts/{enrollment_account_id}/providers/Microsoft.CostManagement/"
        "pricesheets/default/download?api-version=2023-03-01"
    )
    headers = {"Authorization": f"Bearer {access_token}"}
    meta = http_get_json(url, headers=headers)
    download_url = meta.get("properties", {}).get("downloadUrl")
    if not download_url:
        raise RuntimeError("Failed to obtain downloadUrl for EA price sheet")

    resp = http_get(download_url)
    content_type = resp.headers.get("Content-Type", "").lower()
    if "csv" in content_type or download_url.lower().endswith(".csv"):
        text = resp.content.decode("utf-8", errors="ignore")
        rows = list(csv.DictReader(text.splitlines()))
        return clean_rows(rows)
    data = http_get_json(download_url)
    if isinstance(data, list) and all(isinstance(x, dict) for x in data):
        return clean_rows(data)
    return data

# ---------- Enterprise Pricing (normalise + lookups) ----------
def enterprise_lookup(ent: Dict[Key, Decimal], service: str, sku: str, region: str, uom: str) -> Optional[Decimal]:
    if not ent:
        return None
    key_with_region = (service, sku, region, uom)
    if key_with_region in ent:
        return ent[key_with_region]
    # Some sheets omit region per meter
    key_without_region = (service, sku, "", uom)
    return ent.get(key_without_region)

def load_enterprise_csv(path: str) -> Dict[Key, Decimal]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # Clean to canonical headings first, then build the price map
    return normalise_enterprise_rows(clean_rows(rows))

def normalise_enterprise_rows(rows: List[Dict[str, Any]]) -> Dict[Key, Decimal]:
    """
    Build the enterprise price map from rows already cleaned to canonical headings.
    Keys: (serviceName, skuName or meterName or armSkuName, armRegionName, unitOfMeasure)
    Value: Decimal(unitPrice) — falling back to retailPrice if needed.
    """
    out: Dict[Key, Decimal] = {}
    for r in rows:
        service = (r.get("serviceName") or r.get("productName") or "").strip()
        # Prefer skuName; fall back to meterName or armSkuName if skuName is missing
        sku = (r.get("skuName") or r.get("meterName") or r.get("armSkuName") or "").strip()
        region = (r.get("armRegionName") or "").strip()
        uom = (r.get("unitOfMeasure") or "").strip()
        price_str = r.get("unitPrice") or r.get("retailPrice") or "0"
        key: Key = (service, sku, region, uom)
        try:
            out[key] = decimal(price_str)
        except Exception:
            # Skip rows with non-numeric price
            continue
    return out