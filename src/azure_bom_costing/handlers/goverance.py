# =====================================================================================
# Governance / Policy (generally $0; Defender handled elsewhere)
# =====================================================================================
from decimal import Decimal
from typing import Dict

from ..helpers import _d
from ..types import Key

def price_governance(component, region, currency, ent_prices: Dict[Key, Decimal]):
    return _d(0), "Governance (Policy/Advisor/Blueprints typically $0)"