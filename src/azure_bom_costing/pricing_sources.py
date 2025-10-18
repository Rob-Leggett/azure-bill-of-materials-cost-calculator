# pricing_sources.py
from __future__ import annotations
import csv
import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote
import requests

RETAIL_API = "https://prices.azure.com/api/retail/prices?api-version=2023-01-01-preview"
MGMT_SCOPE = "https://management.azure.com/.default"

# ---------- money & decimal helpers ----------
def money(v) -> Decimal:
    return Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def d(val, default=Decimal(0)) -> Decimal:
    if isinstance(val, Decimal):
        return val
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal(default)

# ---------- HTTP helpers ----------
def http_get_json(url: str, headers: Optional[Dict[str, str]] = None) -> dict:
    r = requests.get(url, headers=headers or {}, timeout=60)
    r.raise_for_status()
    return r.json()

def http_get(url: str, headers: Optional[Dict[str, str]] = None) -> requests.Response:
    r = requests.get(url, headers=headers or {}, timeout=300, stream=True)
    r.raise_for_status()
    return r

# ---------- AAD token for Enterprise API ----------
def get_aad_token(tenant_id: str, client_id: str, client_secret: str, scope: str = MGMT_SCOPE) -> str:
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": scope,
        "grant_type": "client_credentials",
    }
    r = requests.post(token_url, data=data, timeout=60)
    r.raise_for_status()
    return r.json()["access_token"]

# ---------- Enterprise price sheet (MCA / EA) ----------
def download_price_sheet_mca(access_token: str, billing_account_id: str) -> List[Dict[str, str]]:
    url = f"https://management.azure.com/providers/Microsoft.Billing/billingAccounts/{billing_account_id}/providers/Microsoft.CostManagement/pricesheets/default/download?api-version=2023-03-01"
    headers = {"Authorization": f"Bearer {access_token}"}
    meta = http_get_json(url, headers=headers)
    download_url = meta.get("properties", {}).get("downloadUrl")
    if not download_url:
        raise RuntimeError("Failed to obtain downloadUrl for MCA price sheet")
    resp = http_get(download_url)
    content_type = resp.headers.get("Content-Type", "").lower()
    if "csv" in content_type or download_url.lower().endswith(".csv"):
        text = resp.content.decode("utf-8", errors="ignore")
        return list(csv.DictReader(text.splitlines()))
    try:
        return http_get_json(download_url)
    except Exception:
        raise RuntimeError("Unknown price sheet format; expected CSV")

def download_price_sheet_ea(access_token: str, enrollment_account_id: str) -> List[Dict[str, str]]:
    url = f"https://management.azure.com/providers/Microsoft.Billing/enrollmentAccounts/{enrollment_account_id}/providers/Microsoft.CostManagement/pricesheets/default/download?api-version=2023-03-01"
    headers = {"Authorization": f"Bearer {access_token}"}
    meta = http_get_json(url, headers=headers)
    download_url = meta.get("properties", {}).get("downloadUrl")
    if not download_url:
        raise RuntimeError("Failed to obtain downloadUrl for EA price sheet")
    resp = http_get(download_url)
    content_type = resp.headers.get("Content-Type", "").lower()
    if "csv" in content_type or download_url.lower().endswith(".csv"):
        text = resp.content.decode("utf-8", errors="ignore")
        return list(csv.DictReader(text.splitlines()))
    try:
        return http_get_json(download_url)
    except Exception:
        raise RuntimeError("Unknown price sheet format; expected CSV")

# ---------- Normalise enterprise rows ----------
Key = Tuple[str, str, str, str]  # (serviceName, skuName, region, unitOfMeasure)

def normalise_enterprise_rows(rows: List[Dict[str, str]]) -> Dict[Key, Decimal]:
    out: Dict[Key, Decimal] = {}
    for r in rows:
        service = r.get("ServiceName") or r.get("serviceName") or r.get("ProductName") or ""
        sku = r.get("SkuName") or r.get("skuName") or r.get("MeterName") or r.get("ArmSkuName") or ""
        region = (r.get("armRegionName") or r.get("ArmRegionName") or r.get("Region") or r.get("Location") or "" ).strip()
        uom = r.get("UnitOfMeasure") or r.get("unitOfMeasure") or r.get("UnitOfMeasureDisplay") or ""
        price = r.get("UnitPrice") or r.get("unitPrice") or r.get("DiscountedPrice") or r.get("retailPrice") or "0"
        key = (service.strip(), sku.strip(), region.strip(), uom.strip())
        try:
            out[key] = d(price)
        except Exception:
            continue
    return out

def load_enterprise_csv(path: str) -> Dict[Key, Decimal]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return normalise_enterprise_rows(rows)

def enterprise_lookup(ent: Dict[Key, Decimal], service: str, sku: str, region: str, uom: str) -> Optional[Decimal]:
    if not ent:
        return None
    key = (service, sku, region, uom)
    if key in ent:
        return ent[key]
    # Some sheets omit region per meter
    key2 = (service, sku, "", uom)
    return ent.get(key2)

# ---------- Retail Prices API ----------
def retail_fetch_items(filter_expr: str, currency: str) -> List[dict]:
    items = []
    url = f"{RETAIL_API}&$filter={quote(filter_expr)}&currencyCode={currency}"
    while url:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        data = r.json()
        items.extend(data.get("Items", []))
        url = data.get("NextPageLink")
    return items

def retail_pick(items: List[dict], prefer_uom: Optional[str] = None) -> Optional[dict]:
    if not items:
        return None
    if prefer_uom:
        for i in items:
            if i.get("unitOfMeasure") == prefer_uom and i.get("retailPrice", 0) > 0:
                return i
    for i in items:
        if i.get("retailPrice", 0) > 0:
            return i
    return items[0]