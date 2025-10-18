# =====================================================================================
# DevOps (best-effort; often billed outside Retail Prices API)
# component: { "type":"devops", "parallel_jobs": 2, "extra_users": 5 }
# =====================================================================================
from decimal import Decimal
from typing import Dict

from ..helpers import _d
from ..types import Key


def price_devops(component, region, currency, ent_prices: Dict[Key, Decimal]):
    # Many orgs are $0 here or billed via Marketplace. Keep it safe and transparent.
    return _d(0), "Azure DevOps (not priced via Retail API; adjust manually if needed)"
