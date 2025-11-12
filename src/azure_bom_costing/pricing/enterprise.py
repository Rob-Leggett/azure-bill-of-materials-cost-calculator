from __future__ import annotations
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple

import csv
import gzip
import io
import zipfile

from ..helpers.csv import clean_rows
from ..helpers.http import http_get_json, http_get
from ..helpers.math import decimal
from ..types import Key


# =============================================================================
# Encoding / CSV parsing
# =============================================================================

def _decode_bytes(data: bytes) -> str:
    """
    Decode raw bytes from Azure exports into text.
    Tries common encodings; falls back to utf-8 with replacement.
    """
    for enc in ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "cp1252"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return data.decode("utf-8", errors="replace")


def _csv_rows_from_bytes(data: bytes) -> List[Dict[str, Any]]:
    """
    Convert CSV bytes -> list of dict rows.
    Uses newline='' so Python's csv can handle dialects properly.
    """
    sio = io.StringIO(_decode_bytes(data), newline="")
    return list(csv.DictReader(sio))


# =============================================================================
# HTTP response unpacking (gzip/zip) and polymorphic parsing (CSV/JSON)
# =============================================================================

def _unpack_response_bytes(resp) -> Tuple[bytes, str]:
    """
    Return (raw_bytes, effective_content_type) from an HTTP response.
    - Transparently gunzips if Content-Encoding: gzip
    - If ZIP content, extracts and returns the first CSV entry
    """
    content_type = (resp.headers.get("Content-Type") or "").lower()
    content_enc  = (resp.headers.get("Content-Encoding") or "").lower()
    raw = resp.content

    # Transparent gzip (if signaled)
    if "gzip" in content_enc:
        try:
            raw = gzip.decompress(raw)
        except Exception:
            # If not actually gzip, keep original bytes
            pass

    # ZIP payloads (either content-type says zip or signature PK\x03\x04)
    if "zip" in content_type or (len(raw) > 4 and raw[:4] == b"PK\x03\x04"):
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = zf.namelist()
            if not names:
                return raw, content_type
            # Prefer first .csv; else first file
            target = next((n for n in names if n.lower().endswith(".csv")), names[0])
            with zf.open(target) as f:
                return f.read(), "text/csv"

    return raw, content_type


def _fetch_pricesheet_rows_or_json(download_url: str) -> List[Dict[str, Any]] | dict:
    """
    Fetch the price sheet from a SAS URL and return either:
      - list[dict] (CSV normalized to rows), or
      - dict/list (JSON passthrough if unknown shape; rows if list-of-dicts)
    """
    resp = http_get(download_url)
    raw, ctype = _unpack_response_bytes(resp)

    # CSV path (content-type or file extension)
    if "csv" in ctype or download_url.lower().endswith(".csv"):
        return clean_rows(_csv_rows_from_bytes(raw))

    # Some tenants return JSON
    try:
        data = http_get_json(download_url)
        if isinstance(data, list) and all(isinstance(x, dict) for x in data):
            return clean_rows(data)
        return data
    except Exception:
        # Not valid JSON → try CSV anyway
        return clean_rows(_csv_rows_from_bytes(raw))


# =============================================================================
# Azure Enterprise/MCA price sheet downloads
# =============================================================================

def _download_enterprise_prices(access_token: str, url: str, err_msg: str) -> List[Dict[str, Any]] | dict:
    """
    Common flow:
      1) Call the CostManagement 'download' endpoint to get a short-lived SAS URL
      2) Download content (csv/zip/json)
      3) Normalize/return
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    meta = http_get_json(url, headers=headers)
    download_url = meta.get("properties", {}).get("downloadUrl")
    if not download_url:
        raise RuntimeError(err_msg)
    return _fetch_pricesheet_rows_or_json(download_url)


def download_price_sheet_mca(access_token: str, billing_account_id: str) -> List[Dict[str, Any]] | dict:
    """
    Download the MCA price sheet rows (or JSON passthrough if tenant returns non-tabular data).
    """
    url = (
        "https://management.azure.com/providers/Microsoft.Billing/"
        f"billingAccounts/{billing_account_id}/providers/Microsoft.CostManagement/"
        "pricesheets/default/download?api-version=2023-03-01"
    )
    return _download_enterprise_prices(
        access_token,
        url,
        err_msg="Failed to obtain downloadUrl for MCA price sheet",
    )


def download_price_sheet_ea(access_token: str, enrollment_account_id: str) -> List[Dict[str, Any]] | dict:
    """
    Download the EA price sheet rows (or JSON passthrough if tenant returns non-tabular data).
    """
    url = (
        "https://management.azure.com/providers/Microsoft.Billing/"
        f"enrollmentAccounts/{enrollment_account_id}/providers/Microsoft.CostManagement/"
        "pricesheets/default/download?api-version=2023-03-01"
    )
    return _download_enterprise_prices(
        access_token,
        url,
        err_msg="Failed to obtain downloadUrl for EA price sheet",
    )


# =============================================================================
# Enterprise pricing: normalize + lookups
# =============================================================================

def enterprise_lookup(ent: Dict[Key, Decimal], service: str, sku: str, region: str, uom: str) -> Optional[Decimal]:
    """
    Lookup (service, sku, region, uom) in the enterprise price map.
    Falls back to regionless key if region is missing in sheet.
    """
    if not ent:
        return None
    with_region = (service, sku, region, uom)
    if with_region in ent:
        return ent[with_region]
    without_region = (service, sku, "", uom)
    return ent.get(without_region)


def load_enterprise_csv(path: str) -> Dict[Key, Decimal]:
    """
    Load a locally-saved enterprise CSV (robust to UTF-16) and build a price map.
    """
    with open(path, "rb") as bf:
        raw = bf.read()
    rows = _csv_rows_from_bytes(raw)
    return normalise_enterprise_rows(clean_rows(rows))


def normalise_enterprise_rows(rows: List[Dict[str, Any]]) -> Dict[Key, Decimal]:
    """
    Build the enterprise price map from rows already cleaned to canonical headings.

    Key:   (serviceName, skuName|meterName|armSkuName, armRegionName, unitOfMeasure)
    Value: Decimal(unitPrice), falling back to retailPrice. Keeps the LOWEST positive
           price when duplicates appear.
    """
    out: Dict[Key, Decimal] = {}

    for r in rows:
        service = (r.get("serviceName") or r.get("productName") or "").strip()
        sku     = (r.get("skuName") or r.get("meterName") or r.get("armSkuName") or "").strip()
        region  = (r.get("armRegionName") or "").strip()
        uom     = (r.get("unitOfMeasure") or "").strip()

        price_raw = r.get("unitPrice") or r.get("retailPrice") or "0"
        try:
            px = decimal(price_raw)
        except Exception:
            continue
        if px <= 0:
            continue

        key: Key = (service, sku, region, uom)
        if key in out:
            if px < out[key]:
                out[key] = px
        else:
            out[key] = px

    return out