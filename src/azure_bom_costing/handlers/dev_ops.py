# =====================================================================================
# Azure DevOps (best-effort; not typically billed via Retail Prices API). Example component:
# {
#   "type": "devops",
#   "parallel_jobs": 2,
#   "extra_users": 5
# }
#
# Notes:
# • Models Azure DevOps (Repos, Pipelines, Artifacts, Boards, Test Plans) cost placeholders.
# • Azure DevOps Services are often:
#     - Bundled with Microsoft 365 E3/E5 or Visual Studio subscriptions.
#     - Billed via Marketplace / organization-level billing, not through the standard
#       Azure Retail Prices API.
# • Typical billable elements (if applicable):
#     - Parallel jobs for CI/CD pipelines beyond the included free tier.
#     - Additional basic users (beyond 5 free users per org).
#     - Test Plans licenses (per user/month).
#     - Artifacts storage (per GB).
# • This model intentionally returns $0 for now, serving as a placeholder for manual cost
#   injection or overrides if enterprise DevOps usage is billed separately.
# • Adjust manually when integrating full cost data or Marketplace price sheets.
# =====================================================================================
from decimal import Decimal
from typing import Dict

from ..helpers import _d
from ..types import Key


def price_devops(component, region, currency, ent_prices: Dict[Key, Decimal]):
    # Many orgs are $0 here or billed via Marketplace. Keep it safe and transparent.
    return _d(0), "Azure DevOps (not priced via Retail API; adjust manually if needed)"
