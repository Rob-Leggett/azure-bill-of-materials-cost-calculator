from __future__ import annotations

from decimal import Decimal
from urllib.parse import quote as url_quote
from typing import Optional, Dict, List, Callable, Any

from ..helpers.csv import clean_rows, ALLOWED_HEADINGS
from ..helpers.file import filesize
from ..helpers.http import get_session
from ..helpers.math import decimal
from ..types import Key

import csv
import os
import time
import re

RETAIL_API = "https://prices.azure.com/api/retail/prices?api-version=2023-01-01-preview"
_DEFAULT_RETAIL_CSV: Optional[str] = None
_RETAIL_INDEX: Optional[Dict[Key, Decimal]] = None

def set_default_retail_csv(path: Optional[str]) -> None:
    """Set a default retail CSV path for all retail fetches/lookup."""
    global _DEFAULT_RETAIL_CSV, _RETAIL_INDEX
    _DEFAULT_RETAIL_CSV = path
    _RETAIL_INDEX = None  # force rebuild if used later

def get_default_retail_csv() -> Optional[str]:
    return _DEFAULT_RETAIL_CSV

def ensure_retail_cache(path: str, currency: str = "USD", *, filter_expr: Optional[str] = None) -> None:
    """
    If the CSV doesn't exist (or is empty), download it (optionally filtered) and save to path.
    """
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    retail_download_to_csv(path, currency=currency, filter_expr=filter_expr, sleep_between_pages=0.0)

def retail_download_to_csv(
        out_csv_path: str,
        currency: str = "AUD",
        filter_expr: Optional[str] = None,
        sleep_between_pages: float = 0.0,
) -> int:
    """
    Download ALL retail price rows (optionally filtered) for a currency and write to CSV.
    Writes only canonical headings defined in _ALLOWED.
    Returns the number of cleaned rows written.
    """
    base = RETAIL_API
    if filter_expr:
        base += f"&$filter={url_quote(filter_expr)}"
    base += f"&currencyCode={currency}"

    session = get_session()
    session.headers.update({"Accept": "application/json"})

    url = base
    rows: List[dict] = []
    seen_urls = set()

    while url:
        if "currencyCode=" not in url:
            joiner = "&" if "?" in url else "?"
            url = f"{url}{joiner}currencyCode={currency}"

        if url in seen_urls:
            break
        seen_urls.add(url)

        r = session.get(url, timeout=120)
        r.raise_for_status()
        data = r.json()
        items = data.get("Items", []) or []
        rows.extend(items)
        url = data.get("NextPageLink")
        if sleep_between_pages and url:
            time.sleep(sleep_between_pages)

    cleaned = clean_rows(rows)

    # Always write a CSV with the canonical header (even if empty)
    with open(out_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(ALLOWED_HEADINGS))
        writer.writeheader()
        if cleaned:
            writer.writerows(cleaned)

    return len(cleaned)

def load_retail_csv(path: str) -> List[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # If the file is already canonical this is a no-op; otherwise it normalises.
    return clean_rows(rows)

# ---- mini filter interpreter for offline CSV ----------------------------------------
_EQ_RE   = re.compile(r"\s*(\w+)\s+eq\s+'([^']*)'\s*", re.IGNORECASE)
_CONTAINS_RE = re.compile(r"\s*contains\(\s*(\w+)\s*,\s*'([^']*)'\s*\)\s*", re.IGNORECASE)

def _parse_simple_filter(filter_expr: str) -> List[Callable[[dict], bool]]:
    if not filter_expr:
        return [lambda _: True]

    parts: List[str] = []
    depth = 0; buf = []
    s = filter_expr
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == '(':
            depth += 1
            buf.append(ch); i += 1; continue
        if ch == ')':
            depth -= 1
            buf.append(ch); i += 1; continue
        if depth == 0 and s[i:i+4].lower() == " and":
            parts.append("".join(buf).strip()); buf = []; i += 4; continue
        buf.append(ch); i += 1
    if buf:
        parts.append("".join(buf).strip())

    preds: List[Callable[[dict], bool]] = []
    for p in parts:
        m = _EQ_RE.fullmatch(p)
        if m:
            field, val = m.group(1), m.group(2)
            fld = field; val_l = val.lower()
            preds.append(lambda row, fld=fld, val_l=val_l: (str(row.get(fld) or "")).lower() == val_l)
            continue
        m = _CONTAINS_RE.fullmatch(p)
        if m:
            field, val = m.group(1), m.group(2)
            fld = field; val_l = val.lower()
            preds.append(lambda row, fld=fld, val_l=val_l: val_l in (str(row.get(fld) or "")).lower())
            continue
        preds.append(lambda row: True)

    return preds

def retail_fetch_items_offline(filter_expr: str, currency: str, offline_csv_path: str) -> List[dict]:
    rows = load_retail_csv(offline_csv_path)  # already cleaned to canonical schema
    preds = _parse_simple_filter(filter_expr)
    out: List[dict] = []
    for r in rows:
        c = (r.get("currencyCode") or "").upper()
        if c and c != (currency or "").upper():
            continue
        ok = True
        for pred in preds:
            if not pred(r):
                ok = False
                break
        if ok:
            out.append(r)
    return out

# ---------- Retail fetch (online; with optional offline CSV override) ----------
def retail_fetch_items(filter_expr: str, currency: str, offline_csv_path: Optional[str] = None) -> List[dict]:
    """
    If offline_csv_path is provided OR a module default CSV is set, fetch from CSV using our mini-filter.
    Otherwise, call the Azure Retail Prices API with full pagination.
    Returns ONLY rows with canonical headings.
    """
    # Prefer an explicit offline path; else the module default
    path = offline_csv_path or _DEFAULT_RETAIL_CSV
    if path:
        # Ensure cache exists; if not, download full currency dataset first
        if not os.path.exists(path) or filesize(path) == 0:
            ensure_retail_cache(path, currency=currency)
        return retail_fetch_items_offline(filter_expr, currency, path)

    # Online path (no CSV configured)
    items: List[dict] = []
    url = f"{RETAIL_API}&$filter={url_quote(filter_expr)}&currencyCode={currency}"

    max_attempts = 4
    backoff = 0.75
    seen_urls = set()
    session = get_session()
    session.headers.update({"Accept": "application/json"})

    while url:
        if "currencyCode=" not in url:
            joiner = "&" if "?" in url else "?"
            url = f"{url}{joiner}currencyCode={currency}"

        if url in seen_urls:
            break
        seen_urls.add(url)

        attempt = 0
        while True:
            attempt += 1
            try:
                r = session.get(url, timeout=60)
                r.raise_for_status()
                data = r.json()
                break
            except Exception:
                if attempt >= max_attempts:
                    raise
                time.sleep(backoff * attempt)

        items.extend(data.get("Items", []) or [])
        url = data.get("NextPageLink")

    return clean_rows(items)

def retail_pick(items: List[dict], prefer_uom: Optional[str] = None) -> Optional[dict]:
    if not items:
        return None
    if prefer_uom:
        for i in items:
            if i.get("unitOfMeasure") == prefer_uom and decimal(i.get("retailPrice") or 0) > 0:
                return i
    for i in items:
        if decimal(i.get("retailPrice") or 0) > 0:
            return i
    return items[0]

# ---------- Retail: normalise to an index + lookup ----------
def normalise_retail_rows(rows: List[Dict[str, Any]]) -> Dict[Key, Decimal]:
    """
    Build a (service, sku|meter|product, region, uom) -> Decimal(price) index.
    Rows MUST be canonical. We choose the lowest positive price for duplicate keys.
    """
    out: Dict[Key, Decimal] = {}
    for r in rows:
        svc = (r.get("serviceName") or "").strip()
        sku = (r.get("skuName") or r.get("meterName") or r.get("productName") or "").strip()
        region = (r.get("armRegionName") or "").strip()
        uom = (r.get("unitOfMeasure") or "").strip()
        price_raw = r.get("retailPrice") or r.get("unitPrice") or 0
        try:
            px = decimal(price_raw)
            if px <= 0:
                continue
        except Exception:
            continue
        key: Key = (svc, sku, region, uom)
        if key in out:
            if px < out[key]:
                out[key] = px
        else:
            out[key] = px
    return out

def load_retail_csv_index(path: str) -> Dict[Key, Decimal]:
    rows = load_retail_csv(path)  # cleaned already
    return normalise_retail_rows(rows)

def _get_or_build_retail_index() -> Optional[Dict[Key, Decimal]]:
    global _RETAIL_INDEX
    if _RETAIL_INDEX is not None:
        return _RETAIL_INDEX
    if not _DEFAULT_RETAIL_CSV:
        return None
    if not os.path.exists(_DEFAULT_RETAIL_CSV) or os.path.getsize(_DEFAULT_RETAIL_CSV) == 0:
        ensure_retail_cache(_DEFAULT_RETAIL_CSV)
    _RETAIL_INDEX = load_retail_csv_index(_DEFAULT_RETAIL_CSV)
    return _RETAIL_INDEX

def retail_lookup(ret_index: Dict[Key, Decimal] | None,
                  service: str,
                  sku: str,
                  region: str,
                  uom: str,
                  *,
                  service_aliases: Optional[List[str]] = None,
                  accept_global_region: bool = True) -> Optional[Decimal]:
    """
    Retail lookup similar to enterprise_lookup. If ret_index is None, it will try the
    module cached index built from the default retail CSV.
    """
    idx = ret_index or _get_or_build_retail_index()
    if not idx:
        return None

    svc = (service or "").strip()
    sk  = (sku or "").strip()
    rgn = (region or "").strip()
    um  = (uom or "").strip()

    # 1) exact
    key = (svc, sk, rgn, um)
    if key in idx:
        return idx[key]

    # 2) regionless
    key_norgn = (svc, sk, "", um)
    if key_norgn in idx:
        return idx[key_norgn]

    # 3) global variants
    if accept_global_region:
        for gr in ("Global", "global"):
            key_glob = (svc, sk, gr, um)
            if key_glob in idx:
                return idx[key_glob]

    # 4) service aliases
    if service_aliases:
        for alias in service_aliases:
            a = (alias or "").strip()
            if not a:
                continue
            k1 = (a, sk, rgn, um)
            if k1 in idx:
                return idx[k1]
            k2 = (a, sk, "", um)
            if k2 in idx:
                return idx[k2]
            if accept_global_region:
                for gr in ("Global", "global"):
                    k3 = (a, sk, gr, um)
                    if k3 in idx:
                        return idx[k3]

    return None