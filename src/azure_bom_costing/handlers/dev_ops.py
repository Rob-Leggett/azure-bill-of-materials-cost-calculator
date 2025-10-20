# =====================================================================================
# Azure DevOps (best-effort; usually NOT billed via Retail Prices API). Example:
# {
#   "type": "devops",
#   "parallel_jobs": 2,
#   "extra_users": 5,
#   "test_plans_users": 0,
#   "artifacts_gb": 0,
#   "overrides": {
#       "parallel_job_per_month": 0.0,   # AUD / job-month
#       "extra_user_per_month": 0.0,     # AUD / user-month (Basic users beyond 5 free)
#       "test_plans_per_month": 0.0,     # AUD / user-month
#       "artifacts_per_gb_month": 0.0    # AUD / GB-month
#   }
# }
#
# Notes:
# • Pricing commonly comes via Marketplace or M365/Visual Studio licenses, not Retail API.
# • This function:
#     1) Looks for Enterprise sheet meters if you’ve loaded one.
#     2) Otherwise uses explicit overrides you provide in the component.
#     3) Otherwise charges $0 (safe default).
# • Enterprise sheet (if present) is probed with these keys:
#     - service="Azure DevOps Services", sku ∈ {"Parallel Jobs","Basic User","Test Plans","Artifacts Storage"}
#     - uom ∈ {"1/Month","1 GB/Month"}
# =====================================================================================
from decimal import Decimal
from typing import Dict

from ..helpers import _d
from ..pricing_sources import enterprise_lookup
from ..types import Key


def price_devops(component, region, currency, ent_prices: Dict[Key, Decimal]):
    # Inputs
    parallel_jobs    = _d(component.get("parallel_jobs", 0))
    extra_users      = _d(component.get("extra_users", 0))          # Basic users beyond 5 free
    test_plans_users = _d(component.get("test_plans_users", 0))     # Optional
    artifacts_gb     = _d(component.get("artifacts_gb", 0))         # Optional (GB-month)
    ov               = (component.get("overrides") or {})

    # Try enterprise sheet first, else use overrides, else 0.
    svc = "Azure DevOps Services"

    def _ent_or_override(sku: str, uom: str, override_key: str) -> Decimal:
        ent = enterprise_lookup(ent_prices, svc, sku, region, uom)
        if ent is not None:
            return _d(ent)
        if override_key in ov and ov[override_key] is not None:
            return _d(ov[override_key])
        return _d(0)

    # Unit rates (per month or per GB-month)
    rate_job   = _ent_or_override("Parallel Jobs",   "1/Month",    "parallel_job_per_month")
    rate_user  = _ent_or_override("Basic User",      "1/Month",    "extra_user_per_month")
    rate_tp    = _ent_or_override("Test Plans",      "1/Month",    "test_plans_per_month")
    rate_art   = _ent_or_override("Artifacts Storage","1 GB/Month","artifacts_per_gb_month")

    # Totals
    cost_jobs = rate_job * parallel_jobs
    cost_user = rate_user * extra_users
    cost_tp   = rate_tp  * test_plans_users
    cost_art  = rate_art * artifacts_gb

    total = cost_jobs + cost_user + cost_tp + cost_art

    # Description
    parts = []
    parts.append(f"jobs:{int(parallel_jobs)} @ {rate_job}/mo")
    parts.append(f"users+:{int(extra_users)} @ {rate_user}/mo")
    if test_plans_users > 0 or rate_tp > 0:
        parts.append(f"testplans:{int(test_plans_users)} @ {rate_tp}/mo")
    if artifacts_gb > 0 or rate_art > 0:
        parts.append(f"artifacts:{artifacts_gb}GB @ {rate_art}/GB-mo")

    return total, "Azure DevOps " + " ".join(parts)