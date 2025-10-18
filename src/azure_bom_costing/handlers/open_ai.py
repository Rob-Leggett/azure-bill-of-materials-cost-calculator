from decimal import Decimal
from typing import List, Dict, Optional

from .common import _per_count_from_text, _text_fields, _arm_region
from ..pricing_sources import d, retail_fetch_items
from ..types import Key

# ---------- Azure OpenAI ----------
def _pick_openai_rate(items: List[dict], want_tokens: bool, direction: Optional[str] = None, want_images: bool = False, want_embeddings: bool = False) -> Optional[dict]:
    """
    Score Azure OpenAI price rows for input/output tokens, images, or embeddings.
    """
    if not items:
        return None

    dir_l = (direction or "").lower()

    def score(i: dict) -> int:
        txt = " ".join([
            i.get("serviceName",""), i.get("productName",""),
            i.get("skuName",""), i.get("meterName","")
        ]).lower()
        s = 0
        if "openai" in txt or "azure ai services" in txt:
            s += 3
        if want_tokens and ("token" in txt or "per 1k" in txt or "1k tokens" in txt):
            s += 6
        if want_images and "image" in txt:
            s += 6
        if want_embeddings and ("embedding" in txt):
            s += 6
        if dir_l:
            if dir_l in txt:
                s += 4
            # common variants
            if dir_l == "input" and ("prompt" in txt or "input" in txt):
                s += 2
            if dir_l == "output" and ("completion" in txt or "output" in txt):
                s += 2
        # prefer explicit 1K-style UOMs
        u = (i.get("unitOfMeasure","") or "").lower()
        if "1k" in u or "1,000" in u or "1000" in u:
            s += 2
        # positive price only
        if d(i.get("retailPrice", 0)) <= 0:
            s -= 100
        return s

    candidates = [i for i in items if d(i.get("retailPrice", 0)) > 0]
    if not candidates:
        return None
    return sorted(candidates, key=score, reverse=True)[0]

def price_ai_openai(component, region, currency, ent_prices: Dict[Key, Decimal]):
    """
    component schema (suggested):
      {
        "type": "ai_openai",
        "deployment": "gpt-4o-mini",
        "input_tokens_1k_per_month": 12000,
        "output_tokens_1k_per_month": 6000,
        "images_generated": 0,
        "embeddings_tokens_1k_per_month": 0,
        "unit_price_overrides": {
            "input_per_1k": 0.0,     # optional AUD override
            "output_per_1k": 0.0,
            "image_each": 0.0,
            "embeddings_per_1k": 0.0
        }
      }
    """
    service_names = ["Azure OpenAI", "Azure AI Services", "Cognitive Services"]
    deployment = component.get("deployment", "")
    dep_l = (deployment or "").lower()

    # Volumes
    in_1k  = d(component.get("input_tokens_1k_per_month", 0))
    out_1k = d(component.get("output_tokens_1k_per_month", 0))
    img_n  = d(component.get("images_generated", 0))
    emb_1k = d(component.get("embeddings_tokens_1k_per_month", 0))

    # Optional per-meter overrides
    ov = component.get("unit_price_overrides", {}) or {}
    in_override  = ov.get("input_per_1k")
    out_override = ov.get("output_per_1k")
    img_override = ov.get("image_each")
    emb_override = ov.get("embeddings_per_1k")

    arm_region = _arm_region(region)

    def fetch_openai_chunks() -> List[dict]:
        filters: List[str] = []
        # Regioned tries
        for svc in service_names:
            filters.append(f"serviceName eq '{svc}' and armRegionName eq '{arm_region}' and priceType eq 'Consumption'")
            if deployment:
                filters.append(f"serviceName eq '{svc}' and armRegionName eq '{arm_region}' and priceType eq 'Consumption' and (contains(productName,'{deployment}') or contains(skuName,'{deployment}') or contains(meterName,'{deployment}'))")
        # Global tries (many OpenAI rows omit region)
        for svc in service_names:
            filters.append(f"serviceName eq '{svc}' and priceType eq 'Consumption'")
            if deployment:
                filters.append(f"serviceName eq '{svc}' and priceType eq 'Consumption' and (contains(productName,'{deployment}') or contains(skuName,'{deployment}') or contains(meterName,'{deployment}'))")

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
        # filter by deployment string lightly if provided (helps reduce cross-model collisions)
        if deployment:
            narrowed = [i for i in items if dep_l in _text_fields(i)]
            if narrowed:
                items = narrowed
        return [i for i in items if d(i.get("retailPrice", 0)) > 0]

    items = fetch_openai_chunks()

    total = d(0)
    details: List[str] = []

    # ---- Input tokens
    if in_1k > 0:
        if in_override is not None:
            unit = d(in_override)
        else:
            row = _pick_openai_rate(items, want_tokens=True, direction="input")
            if not row:
                row = _pick_openai_rate(items, want_tokens=True)  # fallback
            unit = d(row.get("retailPrice", 0)) if row else d(0)
            # Normalize to per 1k if UOM is different
            per = _per_count_from_text(row.get("unitOfMeasure","") if row else "", row or {})
            if per != 1000:
                # unit is per 'per' tokens; we want per 1k
                unit = unit * (d(1000) / per)
        part = unit * in_1k
        total += part
        details.append(f"in:{in_1k}k @ {unit}/1k")

    # ---- Output tokens
    if out_1k > 0:
        if out_override is not None:
            unit = d(out_override)
        else:
            row = _pick_openai_rate(items, want_tokens=True, direction="output")
            if not row:
                row = _pick_openai_rate(items, want_tokens=True)
            unit = d(row.get("retailPrice", 0)) if row else d(0)
            per = _per_count_from_text(row.get("unitOfMeasure","") if row else "", row or {})
            if per != 1000:
                unit = unit * (d(1000) / per)
        part = unit * out_1k
        total += part
        details.append(f"out:{out_1k}k @ {unit}/1k")

    # ---- Images
    if img_n > 0:
        if img_override is not None:
            unit = d(img_override)
        else:
            row = _pick_openai_rate(items, want_tokens=False, want_images=True)
            unit = d(row.get("retailPrice", 0)) if row else d(0)
            # images are typically per each
            per = _per_count_from_text(row.get("unitOfMeasure","") if row else "", row or {})
            if per != 1:
                unit = unit / per
        part = unit * img_n
        total += part
        details.append(f"img:{img_n} @ {unit}/ea")

    # ---- Embeddings
    if emb_1k > 0:
        if emb_override is not None:
            unit = d(emb_override)
        else:
            row = _pick_openai_rate(items, want_tokens=False, want_embeddings=True)
            unit = d(row.get("retailPrice", 0)) if row else d(0)
            per = _per_count_from_text(row.get("unitOfMeasure","") if row else "", row or {})
            if per != 1000:
                unit = unit * (d(1000) / per)
        part = unit * emb_1k
        total += part
        details.append(f"emb:{emb_1k}k @ {unit}/1k")

    if not details:
        return d(0), "Azure OpenAI (no usage provided)"
    return total, "OpenAI " + " ".join(details)

