# =====================================================================================
# Azure OpenAI Service. Example component:
# {
#   "type": "ai_openai",
#   "deployment": "gpt-4o-mini",
#   "input_tokens_1k_per_month": 12000,
#   "output_tokens_1k_per_month": 6000,
#   "images_generated": 0,
#   "embeddings_tokens_1k_per_month": 0,
#   "unit_price_overrides": {
#     "input_per_1k": 0.0,      # Optional override in AUD
#     "output_per_1k": 0.0,
#     "image_each": 0.0,
#     "embeddings_per_1k": 0.0
#   }
# }
#
# Notes:
# • Supports token-based, image, and embedding usage billing for Azure OpenAI models.
# • `deployment` – Model identifier (e.g. “gpt-4o”, “gpt-4o-mini”, “text-embedding-3-small”).
# • `input_tokens_1k_per_month` – Prompt tokens (in 1K units).
# • `output_tokens_1k_per_month` – Completion tokens (in 1K units).
# • `images_generated` – Number of generated images (billed per image).
# • `embeddings_tokens_1k_per_month` – Embedding token volume (1K units).
# • `unit_price_overrides` – Optional structure to manually override per-unit prices
#   when testing or modelling outside live API rates.
# • Billing units:
#     - Input/output tokens: “per 1K tokens”
#     - Images: “per each”
#     - Embeddings: “per 1K tokens”
# • Automatically scores the Azure Retail API catalog for correct meters by direction
#   (input/output), token type, or image/embedding workloads.
# • Used to estimate monthly AI cost per model deployment, aligned with Azure pricing.
# =====================================================================================
from decimal import Decimal
from typing import List, Dict, Optional, Tuple

from ..helpers import _d, _per_count_from_text, _text_fields, _arm_region
from ..pricing_sources import retail_fetch_items, enterprise_lookup
from ..types import Key

# ---------- Azure OpenAI ----------
_SERVICE_CANDIDATES = ["Azure OpenAI", "Azure AI Services", "Cognitive Services"]

def _ent_lookup_many(ent_prices: Dict[Key, Decimal],
                     services: List[str],
                     sku_candidates: List[str],
                     region: str,
                     uom_candidates: List[str]) -> Optional[Tuple[Decimal, str, str]]:
    """
    Try multiple (service, sku, uom) combinations against enterprise sheet.
    Returns (price, matched_sku, matched_uom) on first hit.
    """
    for svc in services:
        for sku in sku_candidates:
            for uom in uom_candidates:
                ent = enterprise_lookup(ent_prices, svc, sku, region, uom)
                if ent is not None:
                    return ent, sku, uom
                # Some sheets omit region:
                ent = enterprise_lookup(ent_prices, svc, sku, "", uom)
                if ent is not None:
                    return ent, sku, uom
    return None


def _normalize_per(unit_price: Decimal, uom: str, sku_text: str, target_per: int) -> Decimal:
    """
    Normalize a price expressed as "per <n>" to a desired unit size (target_per).
    Example: if uom is "1,000" and target_per=1000, it's already normalized.
             if uom is "1" and target_per=1000, multiply by 1000.
    """
    per = _per_count_from_text(uom or "", {"skuName": sku_text}) or _d(0)
    if per <= 0:
        # Try extracting from sku/product text if UOM is unclear
        per = _per_count_from_text("", {"skuName": sku_text}) or _d(target_per)
    return unit_price * (_d(target_per) / per)


def _build_sku_candidates(deployment: str, kind: str) -> List[str]:
    """
    Generate likely enterprise SKU names. `kind` is one of: 'input', 'output', 'image', 'embed'.
    """
    dep = (deployment or "").strip()
    kws = {
        "input": ["Input Tokens", "Prompt Tokens", "Tokens - Input", "Tokens (Input)", "Input"],
        "output": ["Output Tokens", "Completion Tokens", "Tokens - Output", "Tokens (Output)", "Output"],
        "image": ["Image Generation", "Images", "Image", "DALL-E"],
        "embed": ["Embeddings", "Embedding Tokens", "Text Embedding", "Embeddings Tokens"],
    }[kind]

    variants = []
    for k in kws:
        if dep:
            variants += [
                f"{dep} {k}",
                f"{dep} - {k}",
                f"{k} - {dep}",
                f"{k} ({dep})",
            ]
        variants.append(k)
    # De-dup while preserving order
    seen, out = set(), []
    for v in variants:
        if v not in seen:
            out.append(v); seen.add(v)
    return out


def _uom_candidates(kind: str) -> List[str]:
    if kind in ("input", "output", "embed"):
        return ["1,000", "1000", "1K", "per 1K", "Per 1K Tokens", "1K tokens", "Per 1,000"]
    if kind == "image":
        return ["1", "Each", "1 Each", "Per Image"]
    return ["1"]


def _score_openai_retail_row(i: dict,
                             want_tokens: bool,
                             direction: Optional[str] = None,
                             want_images: bool = False,
                             want_embeddings: bool = False) -> int:
    """Score retail rows for Azure OpenAI."""
    price = _d(i.get("retailPrice", 0))
    if price <= 0:
        return -999

    txt = " ".join([
        i.get("serviceName",""), i.get("productName",""),
        i.get("skuName",""), i.get("meterName","")
    ]).lower()

    s = 0
    if "openai" in txt or "azure ai services" in txt or "cognitive services" in txt:
        s += 3
    if want_tokens and ("token" in txt or "1k" in txt or "per 1k" in txt):
        s += 6
    if want_images and "image" in txt:
        s += 6
    if want_embeddings and "embedding" in txt:
        s += 6

    dir_l = (direction or "").lower()
    if dir_l:
        if dir_l in txt:
            s += 4
        if dir_l == "input" and ("prompt" in txt or "input" in txt):
            s += 2
        if dir_l == "output" and ("completion" in txt or "output" in txt):
            s += 2

    # Prefer clear UOMs
    u = (i.get("unitOfMeasure","") or "").lower()
    if "1k" in u or "1,000" in u or "1000" in u:
        s += 2
    if want_images and (u in {"1", "each", "1 each"}):
        s += 2

    return s


def _retail_pick_openai(items: List[dict], want_tokens: bool,
                        direction: Optional[str] = None,
                        want_images: bool = False,
                        want_embeddings: bool = False) -> Optional[dict]:
    rows = [i for i in items if _d(i.get("retailPrice", 0)) > 0]
    if not rows:
        return None
    rows.sort(key=lambda r: _score_openai_retail_row(
        r, want_tokens, direction, want_images, want_embeddings
    ), reverse=True)
    return rows[0]


# ---------- main ----------

def price_ai_openai(component, region, currency, ent_prices: Dict[Key, Decimal]):
    """
    component schema:
      {
        "type": "ai_openai",
        "deployment": "gpt-4o-mini",
        "input_tokens_1k_per_month": 12000,
        "output_tokens_1k_per_month": 6000,
        "images_generated": 0,
        "embeddings_tokens_1k_per_month": 0,
        "unit_price_overrides": { "input_per_1k": 0, "output_per_1k": 0, "image_each": 0, "embeddings_per_1k": 0 }
      }
    """
    deployment = (component.get("deployment") or "").strip()
    dep_l = deployment.lower()

    # Volumes
    in_1k  = _d(component.get("input_tokens_1k_per_month", 0))
    out_1k = _d(component.get("output_tokens_1k_per_month", 0))
    img_n  = _d(component.get("images_generated", 0))
    emb_1k = _d(component.get("embeddings_tokens_1k_per_month", 0))

    # Overrides
    ov = component.get("unit_price_overrides", {}) or {}
    in_override  = ov.get("input_per_1k")
    out_override = ov.get("output_per_1k")
    img_override = ov.get("image_each")
    emb_override = ov.get("embeddings_per_1k")

    arm_region = _arm_region(region)

    # Pre-fetch retail chunks once (covers regioned + global across service name variants)
    def fetch_openai_retail() -> List[dict]:
        filters: List[str] = []
        for svc in _SERVICE_CANDIDATES:
            # Regioned
            filters.append(f"serviceName eq '{svc}' and armRegionName eq '{arm_region}' and priceType eq 'Consumption'")
            if deployment:
                filters.append(
                    f"serviceName eq '{svc}' and armRegionName eq '{arm_region}' and priceType eq 'Consumption' "
                    f"and (contains(productName,'{deployment}') or contains(skuName,'{deployment}') or contains(meterName,'{deployment}'))"
                )
            # Global
            filters.append(f"serviceName eq '{svc}' and priceType eq 'Consumption'")
            if deployment:
                filters.append(
                    f"serviceName eq '{svc}' and priceType eq 'Consumption' "
                    f"and (contains(productName,'{deployment}') or contains(skuName,'{deployment}') or contains(meterName,'{deployment}'))"
                )

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

        # If a deployment string exists, lightly narrow by it (but keep some breadth)
        if deployment:
            narrowed = [i for i in items if dep_l in _text_fields(i)]
            if narrowed:
                items = narrowed
        return [i for i in items if _d(i.get("retailPrice", 0)) > 0]

    retail_items = fetch_openai_retail()

    total = _d(0)
    parts: List[str] = []

    # ----- INPUT TOKENS (per 1k)
    if in_1k > 0:
        if in_override is not None:
            unit_in_1k = _d(in_override)
        else:
            # Enterprise first
            ent_hit = _ent_lookup_many(
                ent_prices,
                _SERVICE_CANDIDATES,
                _build_sku_candidates(deployment, "input"),
                region,
                _uom_candidates("input"),
            )
            if ent_hit:
                ent_price, ent_sku, ent_uom = ent_hit
                unit_in_1k = _normalize_per(ent_price, ent_uom, ent_sku, 1000)
            else:
                # Retail fallback
                row = _retail_pick_openai(retail_items, want_tokens=True, direction="input")
                if not row:
                    row = _retail_pick_openai(retail_items, want_tokens=True)
                unit_in_1k = _normalize_per(
                    _d(row.get("retailPrice", 0)) if row else _d(0),
                    (row.get("unitOfMeasure","") if row else ""),
                    " ".join([row.get("skuName",""), row.get("meterName","")]) if row else "",
                    1000
                )
        cost = unit_in_1k * in_1k
        total += cost
        parts.append(f"in:{in_1k}k @ {unit_in_1k}/1k")

    # ----- OUTPUT TOKENS (per 1k)
    if out_1k > 0:
        if out_override is not None:
            unit_out_1k = _d(out_override)
        else:
            ent_hit = _ent_lookup_many(
                ent_prices,
                _SERVICE_CANDIDATES,
                _build_sku_candidates(deployment, "output"),
                region,
                _uom_candidates("output"),
            )
            if ent_hit:
                ent_price, ent_sku, ent_uom = ent_hit
                unit_out_1k = _normalize_per(ent_price, ent_uom, ent_sku, 1000)
            else:
                row = _retail_pick_openai(retail_items, want_tokens=True, direction="output")
                if not row:
                    row = _retail_pick_openai(retail_items, want_tokens=True)
                unit_out_1k = _normalize_per(
                    _d(row.get("retailPrice", 0)) if row else _d(0),
                    (row.get("unitOfMeasure","") if row else ""),
                    " ".join([row.get("skuName",""), row.get("meterName","")]) if row else "",
                    1000
                )
        cost = unit_out_1k * out_1k
        total += cost
        parts.append(f"out:{out_1k}k @ {unit_out_1k}/1k")

    # ----- IMAGES (per each)
    if img_n > 0:
        if img_override is not None:
            unit_img = _d(img_override)
        else:
            ent_hit = _ent_lookup_many(
                ent_prices,
                _SERVICE_CANDIDATES,
                _build_sku_candidates(deployment, "image"),
                region,
                _uom_candidates("image"),
            )
            if ent_hit:
                ent_price, ent_sku, ent_uom = ent_hit
                unit_img = _normalize_per(ent_price, ent_uom, ent_sku, 1)
            else:
                row = _retail_pick_openai(retail_items, want_tokens=False, want_images=True)
                unit_img = _normalize_per(
                    _d(row.get("retailPrice", 0)) if row else _d(0),
                    (row.get("unitOfMeasure","") if row else ""),
                    " ".join([row.get("skuName",""), row.get("meterName","")]) if row else "",
                    1
                )
        cost = unit_img * img_n
        total += cost
        parts.append(f"img:{img_n} @ {unit_img}/ea")

    # ----- EMBEDDINGS (per 1k)
    if emb_1k > 0:
        if emb_override is not None:
            unit_emb_1k = _d(emb_override)
        else:
            ent_hit = _ent_lookup_many(
                ent_prices,
                _SERVICE_CANDIDATES,
                _build_sku_candidates(deployment, "embed"),
                region,
                _uom_candidates("embed"),
            )
            if ent_hit:
                ent_price, ent_sku, ent_uom = ent_hit
                unit_emb_1k = _normalize_per(ent_price, ent_uom, ent_sku, 1000)
            else:
                row = _retail_pick_openai(retail_items, want_tokens=False, want_embeddings=True)
                unit_emb_1k = _normalize_per(
                    _d(row.get("retailPrice", 0)) if row else _d(0),
                    (row.get("unitOfMeasure","") if row else ""),
                    " ".join([row.get("skuName",""), row.get("meterName","")]) if row else "",
                    1000
                )
        cost = unit_emb_1k * emb_1k
        total += cost
        parts.append(f"emb:{emb_1k}k @ {unit_emb_1k}/1k")

    if not parts:
        return _d(0), "Azure OpenAI (no usage provided)"
    return total, "OpenAI " + " ".join(parts)