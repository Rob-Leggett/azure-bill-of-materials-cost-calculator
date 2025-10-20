# =====================================================================================
# Azure Governance / Policy / Management. Example component:
# {
#   "type": "governance"
# }
#
# Notes:
# • Represents Azure management and governance services such as:
#     - Azure Policy
#     - Azure Blueprints
#     - Azure Advisor
#     - Management Groups / Resource Graph
# • These services are generally billed at $0 (control-plane only).
# • Defender for Cloud coverage and Security Center charges are handled separately.
# • Included for completeness in enterprise cost modelling and tagging frameworks.
# • Returns zero cost by design; used as a placeholder for compliance tracking.
# =====================================================================================
from decimal import Decimal
from typing import Dict

from ..helpers import _d
from ..types import Key

def price_governance(component, region, currency, ent_prices: Dict[Key, Decimal]):
    """
    Intentional $0:
      - Azure Policy, Advisor, Blueprints, Resource Graph, Management Groups are control-plane features.
      - They do not have consumption meters in the Retail Prices API or enterprise price sheets.
      - Security/Defender charges are modelled separately.
    """
    return _d(0), "Governance (Policy/Advisor/Blueprints typically $0)"