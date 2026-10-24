from __future__ import annotations

import errno
import json
import os
import re
import time
from collections.abc import Callable, Iterator
from typing import Any, cast
from urllib.parse import quote as url_quote

from ..helpers.csv import clean_rows
from ..helpers.http import get_session
from ..helpers.math import decimal

# =============================================================================
# Constants & module state
# =============================================================================

RETAIL_API = "https://prices.azure.com/api/retail/prices?api-version=2023-01-01-preview"

# We still keep checkpoint/lock so you can resume a long download
_CHECKPOINT_NAME = "retail-prices"        # base name for checkpoint + lock
_CHECKPOINT_SUFFIX = ".checkpoint"
_LOCK_SUFFIX = ".lock"

_DIR_EXAMPLES = "examples"
_DIR_RETAIL_TEMP = "retail"


# =============================================================================
# Small helpers
# =============================================================================

def _acquire_lock(lock_path: str) -> int:
    """
    Best-effort file lock to avoid concurrent writers to the same temp dir.
    Returns the file descriptor to be closed on release.
    """
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        os.write(fd, str(os.getpid()).encode("utf-8"))
        return fd
    except OSError as e:
        if e.errno == errno.EEXIST:
            raise RuntimeError(f"Lock exists: {lock_path}") from e
        raise


def _release_lock(fd: int | None, lock_path: str) -> None:
    """Release the lock and remove the lock file."""
    try:
        if fd is not None:
            os.close(fd)
    finally:
        try:
            os.remove(lock_path)
        except Exception:
            pass


def _load_checkpoint(cp_path: str) -> dict[str, Any]:
    """
    Return checkpoint dict if present, else {}.
    Keys: next_link, page_no
    """
    try:
        with open(cp_path, encoding="utf-8") as f:
            return cast(dict[str, Any], json.load(f))
    except Exception:
        return {}


def _save_checkpoint(cp_path: str, data: dict[str, Any]) -> None:
    """Atomic checkpoint write."""
    tmp = f"{cp_path}.part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, cp_path)


def _has_positive_price(row: dict[str, Any]) -> bool:
    """
    True if retailPrice or unitPrice is a valid positive number.
    (Useful when searching; not required to save pages.)
    """
    try:
        return decimal(row.get("retailPrice") or row.get("unitPrice") or 0) > 0
    except Exception:
        return False


# =============================================================================
# Downloader: Retail → per-page JSON files
# =============================================================================

def download_retail_pages(
        temp_dir: str = os.path.join(_DIR_EXAMPLES, _DIR_RETAIL_TEMP),
        currency: str = "AUD",
        filter_expr: str | None = None,
        sleep_between_pages: float = 0.03,
) -> int:
    """
    Download the full Retail Prices feed into per-page JSON files:

      examples/temp/retail-prices-1.json
      examples/temp/retail-prices-2.json
      ...

    - Uses a checkpoint file to resume:
        examples/temp/retail-prices.checkpoint
    - Uses a lock file to avoid concurrent runs:
        examples/temp/retail-prices.lock

    Returns: number of JSON pages downloaded (this run, not cumulative).
    """
    os.makedirs(temp_dir, exist_ok=True)

    # Build first URL
    base = RETAIL_API
    if filter_expr:
        base += f"&$filter={url_quote(filter_expr)}"
    base += f"&currencyCode={currency}"

    session = get_session()
    session.headers.update({"Accept": "application/json"})

    cp_path = os.path.join(temp_dir, _CHECKPOINT_NAME + _CHECKPOINT_SUFFIX)
    lock_path = os.path.join(temp_dir, _CHECKPOINT_NAME + _LOCK_SUFFIX)

    # Resume if possible
    cp = _load_checkpoint(cp_path)
    next_url = cp.get("next_link") or base
    page_no = int(cp.get("page_no") or 0)

    lock_fd = _acquire_lock(lock_path)
    try:
        seen_urls: set[str] = set()
        url = next_url
        pages_downloaded = 0

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

            # Bump page number and save raw JSON for this page
            page_no += 1
            pages_downloaded += 1
            debug_path = os.path.join(temp_dir, f"{_CHECKPOINT_NAME}-{page_no}.json")
            try:
                with open(debug_path, "w", encoding="utf-8") as dbg:
                    json.dump(data, dbg, ensure_ascii=False, indent=2)
            except Exception:
                # Don't fail the whole run just because a page on disk failed
                pass

            # Save checkpoint after each page
            next_link = data.get("NextPageLink")
            _save_checkpoint(cp_path, {
                "next_link": next_link,
                "page_no": page_no,
            })

            items = data.get("Items", []) or []
            print(
                f"[page {page_no:>5}] items={len(items):>6} "
                f"(saved as {os.path.basename(debug_path)})",
                end="\r",
            )

            url = next_link
            if url and sleep_between_pages:
                time.sleep(sleep_between_pages)

        # On success, you can keep or delete the checkpoint.
        # Here we keep it so a later run can continue appending pages if Azure adds more.
        print(f"\n[done] downloaded {pages_downloaded} pages into {temp_dir}")
        return pages_downloaded

    finally:
        _release_lock(lock_fd, lock_path)


# =============================================================================
# Local search over saved JSON pages
# =============================================================================

_EQ_RE = re.compile(r"\s*(\w+)\s+eq\s+'([^']*)'\s*", re.IGNORECASE)
_CONTAINS_RE = re.compile(r"\s*contains\(\s*(\w+)\s*,\s*'([^']*)'\s*\)\s*", re.IGNORECASE)

def _parse_simple_filter(filter_expr: str) -> list[Callable[[dict[str, Any]], bool]]:
    """
    Tiny subset of OData $filter:
      - "field eq 'value'"
      - "contains(field,'value')"
      - clauses ANDed together
      - parentheses allowed but ignored for precedence
    """
    if not filter_expr:
        return [lambda _: True]

    # Split by top-level " and "
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    s = filter_expr
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth == 0 and s[i:i+4].lower() == " and":
            parts.append("".join(buf).strip())
            buf = []
            i += 4
            continue
        buf.append(ch)
        i += 1
    if buf:
        parts.append("".join(buf).strip())

    preds: list[Callable[[dict[str, Any]], bool]] = []
    for p in parts:
        m = _EQ_RE.fullmatch(p)
        if m:
            fld, val = m.group(1), m.group(2)
            val_l = val.lower()
            preds.append(_eq_pred(fld, val_l))
            continue

        m = _CONTAINS_RE.fullmatch(p)
        if m:
            fld, val = m.group(1), m.group(2)
            val_l = val.lower()
            preds.append(_contains_pred(fld, val_l))
            continue

        # Unknown clause → accept all (permissive)
        preds.append(lambda row: True)

    return preds


def _eq_pred(fld: str, val_l: str) -> Callable[[dict[str, Any]], bool]:
    return lambda row: str(row.get(fld) or "").lower() == val_l


def _contains_pred(fld: str, val_l: str) -> Callable[[dict[str, Any]], bool]:
    return lambda row: val_l in str(row.get(fld) or "").lower()


def _iter_saved_pages(temp_dir: str) -> Iterator[dict[str, Any]]:
    """
    Yield raw JSON page dicts from temp_dir, ordered by page number.
    """
    if not os.path.isdir(temp_dir):
        return
    # Files look like retail-prices-<n>.json
    names = [
        n for n in os.listdir(temp_dir)
        if n.startswith(_CHECKPOINT_NAME + "-") and n.endswith(".json")
    ]
    # Sort by numeric suffix if possible
    def _page_key(name: str) -> int:
        base = name[len(_CHECKPOINT_NAME) + 1:-5]  # strip 'retail-prices-' and '.json'
        try:
            return int(base)
        except ValueError:
            return 0

    for name in sorted(names, key=_page_key):
        path = os.path.join(temp_dir, name)
        try:
            with open(path, encoding="utf-8") as f:
                yield json.load(f)
        except Exception:
            # Skip corrupt page files
            continue


def _iter_saved_items(temp_dir: str) -> Iterator[dict[str, Any]]:
    """
    Yield individual item dicts from all saved pages.
    """
    for page in _iter_saved_pages(temp_dir):
        yield from page.get("Items", []) or []


def search_saved_retail_items(
        filter_expr: str,
        currency: str = "AUD",
        temp_dir: str = os.path.join(_DIR_EXAMPLES, _DIR_RETAIL_TEMP),
        *,
        require_positive_price: bool = False,
) -> list[dict[str, Any]]:
    """
    Search locally saved Retail JSON pages (no live API call).

    Args:
        filter_expr: Simple OData filter (field eq 'x', contains(field,'x'), ANDed).
        currency: Filters by currencyCode column (case-insensitive).
        require_positive_price: If True, only keep rows with positive price.

    Returns: cleaned rows (via clean_rows) matching the filter.
    """
    preds = _parse_simple_filter(filter_expr)
    cur = (currency or "").upper()

    matched: list[dict[str, Any]] = []
    for item in _iter_saved_items(temp_dir):
        # Currency filter
        if cur and (item.get("currencyCode") or "").upper() not in ("", cur):
            continue
        # Optional positive price filter
        if require_positive_price and not _has_positive_price(item):
            continue
        # Filter predicates
        if all(pred(item) for pred in preds):
            matched.append(item)

    # Normalise schema/column names using existing helper
    return clean_rows(matched)


# =============================================================================
# Optional: live API fetch (no temp, no CSV)
# =============================================================================

def retail_fetch_items_live(
        filter_expr: str,
        currency: str,
) -> list[dict[str, Any]]:
    """
    Fetch items directly from the Retail API (no temp files, no CSV).
    Useful if you just want in-memory rows.
    """
    url = f"{RETAIL_API}&$filter={url_quote(filter_expr)}&currencyCode={currency}"
    session = get_session()
    session.headers.update({"Accept": "application/json"})

    items: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    max_attempts, backoff = 4, 0.75

    while url:
        if "currencyCode=" not in url:
            url = f"{url}{'&' if '?' in url else '?'}currencyCode={currency}"

        if url in seen_urls:
            break
        seen_urls.add(url)

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