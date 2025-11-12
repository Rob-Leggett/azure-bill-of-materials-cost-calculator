from __future__ import annotations

from decimal import Decimal
from urllib.parse import quote as url_quote
from typing import Optional, Dict, List, Callable, Any, Tuple

import csv
import errno
import json
import os
import re
import time

from ..helpers.csv import clean_rows, ALLOWED_HEADINGS
from ..helpers.file import filesize
from ..helpers.http import get_session
from ..helpers.math import decimal
from ..types import Key


# =============================================================================
# Constants & module state
# =============================================================================

RETAIL_API = "https://prices.azure.com/api/retail/prices?api-version=2023-01-01-preview"

_DEFAULT_RETAIL_CSV: Optional[str] = None           # path to default offline CSV
_RETAIL_INDEX: Optional[Dict[Key, Decimal]] = None  # (svc, sku, region, uom) -> price

_CHECKPOINT_SUFFIX = ".checkpoint"
_LOCK_SUFFIX = ".lock"


# =============================================================================
# Public config
# =============================================================================

def set_default_retail_csv(path: Optional[str]) -> None:
    """
    Configure a default local CSV cache (used by retail_fetch_items when no path is provided).
    """
    global _DEFAULT_RETAIL_CSV, _RETAIL_INDEX
    _DEFAULT_RETAIL_CSV = path
    _RETAIL_INDEX = None  # force rebuild next time


def get_default_retail_csv() -> Optional[str]:
    """Return the currently configured default retail CSV path (if any)."""
    return _DEFAULT_RETAIL_CSV


def ensure_retail_cache(
        path: str,
        currency: str = "AUD",
        *,
        filter_expr: Optional[str] = None,
        force: bool = False,
) -> None:
    """
    Ensure a CSV cache exists at `path`. If missing or empty (or force=True), download it.
    """
    if not force and os.path.exists(path) and os.path.getsize(path) > 0:
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    retail_download_to_csv(path, currency=currency, filter_expr=filter_expr, sleep_between_pages=0.0)


# =============================================================================
# Small helpers
# =============================================================================

def _has_positive_price(row: dict) -> bool:
    """
    True if retailPrice or unitPrice is a valid positive number.
    (We write only positive priced rows into the CSV.)
    """
    try:
        return decimal(row.get("retailPrice") or row.get("unitPrice") or 0) > 0
    except Exception:
        return False


def _acquire_lock(lock_path: str):
    """
    Best-effort file lock to avoid concurrent writers to the same CSV.
    Returns the file descriptor to be closed on release.
    """
    fd = None
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        os.write(fd, str(os.getpid()).encode("utf-8"))
        return fd
    except OSError as e:
        if e.errno == errno.EEXIST:
            raise RuntimeError(f"Lock exists: {lock_path}")
        raise


def _release_lock(fd, lock_path: str) -> None:
    """Release the lock and remove the lock file."""
    try:
        if fd is not None:
            os.close(fd)
    finally:
        try:
            os.remove(lock_path)
        except Exception:
            pass


def _load_checkpoint(cp_path: str) -> dict:
    """
    Return checkpoint dict if present, else {}.
    Keys: next_link, rows_written, page_no
    """
    try:
        with open(cp_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_checkpoint(cp_path: str, data: dict) -> None:
    """Atomic checkpoint write."""
    tmp = f"{cp_path}.part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, cp_path)


# =============================================================================
# Streamed downloader (retail → CSV)
# =============================================================================

def retail_download_to_csv(
        out_csv_path: str,
        currency: str = "AUD",
        filter_expr: Optional[str] = None,
        sleep_between_pages: float = 0.03,  # gentle throttle helps under heavy paging
) -> int:
    """
    Stream the full Retail Prices API into CSV:
      - Writes header once, then rows page-by-page
      - Skips zero/negative prices
      - Uses a .checkpoint file to resume in case of interruption
      - Writes to out_csv_path.part and atomically swaps at the end
      - Adds a final newline to avoid truncation/last-line issues
    Returns: total rows written.
    """
    # Build first URL
    base = RETAIL_API
    if filter_expr:
        base += f"&$filter={url_quote(filter_expr)}"
    base += f"&currencyCode={currency}"

    session = get_session()
    session.headers.update({"Accept": "application/json"})

    os.makedirs(os.path.dirname(out_csv_path) or ".", exist_ok=True)
    tmp_path = f"{out_csv_path}.part"
    cp_path = f"{out_csv_path}{_CHECKPOINT_SUFFIX}"
    lock_path = f"{out_csv_path}{_LOCK_SUFFIX}"

    # Resume if possible
    cp = _load_checkpoint(cp_path)
    next_url = cp.get("next_link") or base
    total_written = int(cp.get("rows_written") or 0)
    page_no = int(cp.get("page_no") or 0)

    # Lock to prevent concurrent writers
    lock_fd = _acquire_lock(lock_path)
    try:
        # Open once in append mode; large buffer to reduce syscalls
        file_exists = os.path.exists(tmp_path)
        with open(tmp_path, "a", buffering=1024 * 1024, newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=list(ALLOWED_HEADINGS),
                lineterminator="\n",
                quoting=csv.QUOTE_MINIMAL,
                extrasaction="ignore",  # ignore any unexpected fields
            )
            if not file_exists or os.path.getsize(tmp_path) == 0:
                writer.writeheader()
                f.flush()
                os.fsync(f.fileno())

            seen_urls: set[str] = set()
            url = next_url

            while url:
                # Ensure currency param is always present
                if "currencyCode=" not in url:
                    url = f"{url}{'&' if '?' in url else '?'}currencyCode={currency}"

                # Avoid loops if Azure returns a repeated link
                if url in seen_urls:
                    break
                seen_urls.add(url)

                # GET with retry
                max_attempts, backoff = 4, 0.75
                for attempt in range(1, max_attempts + 1):
                    try:
                        resp = session.get(url, timeout=120)
                        resp.raise_for_status()
                        data = resp.json()
                        break
                    except Exception:
                        if attempt == max_attempts:
                            raise
                        time.sleep(backoff * attempt)

                items = data.get("Items", []) or []
                cleaned = clean_rows(items)

                # Write this page
                page_no += 1
                page_written = 0
                for row in cleaned:
                    # Only write positive prices
                    if _has_positive_price(row):
                        writer.writerow(row)
                        page_written += 1

                total_written += page_written

                # Force page to disk
                f.flush()
                os.fsync(f.fileno())

                # Save checkpoint after each page
                next_link = data.get("NextPageLink")
                _save_checkpoint(cp_path, {
                    "next_link": next_link,
                    "rows_written": total_written,
                    "page_no": page_no,
                })

                print(f"[page {page_no:>5}] wrote {page_written:>7} (total {total_written:>9})", end="\r")

                url = next_link
                if url and sleep_between_pages:
                    time.sleep(sleep_between_pages)

        # Ensure trailing newline (avoids truncated last record on some readers)
        with open(tmp_path, "rb+") as rf:
            rf.seek(0, os.SEEK_END)
            if rf.tell() > 0:
                rf.seek(-1, os.SEEK_END)
                if rf.read(1) != b"\n":
                    rf.write(b"\n")
                    rf.flush()
                    os.fsync(rf.fileno())

        # Atomic replace
        os.replace(tmp_path, out_csv_path)

        # Verify physical line count ~= logical written rows (minus header)
        with open(out_csv_path, "r", encoding="utf-8", newline="") as rf:
            physical_lines = sum(1 for _ in rf)
        print(f"\n[verify] file rows={max(0, physical_lines - 1):,} vs counter={total_written:,}")

        # Success → remove checkpoint
        try:
            os.remove(cp_path)
        except Exception:
            pass

        return total_written

    finally:
        # Keep .part/.checkpoint on failure to allow resume; always release lock
        _release_lock(lock_fd, lock_path)


def load_retail_csv(path: str) -> List[dict]:
    """Load a canonicalised CSV file (normalises column names via clean_rows)."""
    with open(path, newline="", encoding="utf-8") as f:
        return clean_rows(list(csv.DictReader(f)))


# =============================================================================
# Offline filter (simple OData-ish interpreter)
# =============================================================================

_EQ_RE = re.compile(r"\s*(\w+)\s+eq\s+'([^']*)'\s*", re.IGNORECASE)
_CONTAINS_RE = re.compile(r"\s*contains\(\s*(\w+)\s*,\s*'([^']*)'\s*\)\s*", re.IGNORECASE)

def _parse_simple_filter(filter_expr: str) -> List[Callable[[dict], bool]]:
    """
    Very small subset of $filter: "field eq 'value'" ANDed together,
    plus contains(field,'value'). Parentheses allowed (ignored for precedence).
    """
    if not filter_expr:
        return [lambda _: True]

    # Split by top-level " and "
    parts: List[str] = []
    depth, buf = 0, []
    s = filter_expr
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        # detect " and " at top level
        if depth == 0 and s[i:i+4].lower() == " and":
            parts.append("".join(buf).strip())
            buf = []
            i += 4
            continue
        buf.append(ch)
        i += 1
    if buf:
        parts.append("".join(buf).strip())

    preds: List[Callable[[dict], bool]] = []
    for p in parts:
        m = _EQ_RE.fullmatch(p)
        if m:
            fld, val = m.group(1), m.group(2)
            val_l = val.lower()
            preds.append(lambda row, fld=fld, val_l=val_l: (str(row.get(fld) or "")).lower() == val_l)
            continue
        m = _CONTAINS_RE.fullmatch(p)
        if m:
            fld, val = m.group(1), m.group(2)
            val_l = val.lower()
            preds.append(lambda row, fld=fld, val_l=val_l: val_l in (str(row.get(fld) or "")).lower())
            continue
        # Unknown clause → accept all (permissive)
        preds.append(lambda row: True)

    return preds


def retail_fetch_items_offline(filter_expr: str, currency: str, offline_csv_path: str) -> List[dict]:
    """
    Filter rows from a local CSV cache using the simple predicate parser above.
    Currency is applied by matching the 'currencyCode' column.
    """
    rows = load_retail_csv(offline_csv_path)
    preds = _parse_simple_filter(filter_expr)

    out: List[dict] = []
    cur = (currency or "").upper()
    for r in rows:
        if (r.get("currencyCode") or "").upper() not in ("", cur) and cur:
            continue
        if all(pred(r) for pred in preds):
            out.append(r)
    return out


# =============================================================================
# Online fetch (live API) with optional offline override
# =============================================================================

def retail_fetch_items(
        filter_expr: str,
        currency: str,
        offline_csv_path: Optional[str] = None,
) -> List[dict]:
    """
    Fetch retail items with full pagination.
    - If offline_csv_path or default CSV is configured, read from CSV with mini-filter.
    - Else, call Azure Retail API (paginated) and return cleaned items.
    """
    # Use offline cache if given or globally configured
    path = offline_csv_path or _DEFAULT_RETAIL_CSV
    if path:
        if not os.path.exists(path) or filesize(path) == 0:
            ensure_retail_cache(path, currency=currency)
        return retail_fetch_items_offline(filter_expr, currency, path)

    # Live API path
    url = f"{RETAIL_API}&$filter={url_quote(filter_expr)}&currencyCode={currency}"
    session = get_session()
    session.headers.update({"Accept": "application/json"})

    items: List[dict] = []
    seen_urls: set[str] = set()
    max_attempts, backoff = 4, 0.75

    while url:
        if "currencyCode=" not in url:
            url = f"{url}{'&' if '?' in url else '?'}currencyCode={currency}"

        if url in seen_urls:
            break
        seen_urls.add(url)

        # GET with retry
        for attempt in range(1, max_attempts + 1):
            try:
                r = session.get(url, timeout=60)
                r.raise_for_status()
                data = r.json()
                break
            except Exception:
                if attempt == max_attempts:
                    raise
                time.sleep(backoff * attempt)

        items.extend(data.get("Items", []) or [])
        url = data.get("NextPageLink")

    return clean_rows(items)


# =============================================================================
# Retail index and lookup
# =============================================================================

def normalise_retail_rows(rows: List[Dict[str, Any]]) -> Dict[Key, Decimal]:
    """
    Build (service, sku|meter|product, region, uom) -> lowest positive Decimal(price).
    Rows must already be canonical (via clean_rows).
    """
    out: Dict[Key, Decimal] = {}
    for r in rows:
        service = (r.get("serviceName") or "").strip()
        sku     = (r.get("skuName") or r.get("meterName") or r.get("productName") or "").strip()
        region  = (r.get("armRegionName") or "").strip()
        uom     = (r.get("unitOfMeasure") or "").strip()
        price_s = r.get("retailPrice") or r.get("unitPrice") or 0

        try:
            px = decimal(price_s)
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


def load_retail_csv_index(path: str) -> Dict[Key, Decimal]:
    """Load a CSV from disk and return the (svc, sku, region, uom) → price map."""
    return normalise_retail_rows(load_retail_csv(path))


def _get_or_build_retail_index() -> Optional[Dict[Key, Decimal]]:
    """
    Lazily build and cache the retail index from the default CSV path (if configured).
    """
    global _RETAIL_INDEX
    if _RETAIL_INDEX is not None:
        return _RETAIL_INDEX
    if not _DEFAULT_RETAIL_CSV:
        return None
    if not os.path.exists(_DEFAULT_RETAIL_CSV) or os.path.getsize(_DEFAULT_RETAIL_CSV) == 0:
        ensure_retail_cache(_DEFAULT_RETAIL_CSV)
    _RETAIL_INDEX = load_retail_csv_index(_DEFAULT_RETAIL_CSV)
    return _RETAIL_INDEX


def retail_lookup(
        ret_index: Optional[Dict[Key, Decimal]],
        service: str,
        sku: str,
        region: str,
        uom: str,
        *,
        service_aliases: Optional[List[str]] = None,
        accept_global_region: bool = True,
) -> Optional[Decimal]:
    """
    Lookup a price from a retail index with some flexibility:
      1) Exact (svc, sku, region, uom)
      2) Regionless (svc, sku, "", uom)
      3) Global region variants ("Global"/"global")
      4) Service aliases (same sequence)
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