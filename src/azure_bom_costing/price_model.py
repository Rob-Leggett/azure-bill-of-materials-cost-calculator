from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Callable, Dict, Optional, Tuple

from .handlers.api_management import price_api_management
from .handlers.app_insights import price_app_insights
from .handlers.app_service import price_app_service
from .handlers.backup import price_backup
from .handlers.cognitive_search import price_cognitive_search
from .handlers.container_apps import price_container_apps
from .handlers.data_bricks import price_databricks
from .handlers.data_factory import price_data_factory
from .handlers.defender import price_defender
from .handlers.dev_ops import price_dev_ops
from .handlers.dns import price_dns
from .handlers.egress import price_egress
from .handlers.entra_id import price_entra_id
from .handlers.event_hubs import price_event_hubs
from .handlers.fabric import price_fabric
from .handlers.front_door import price_front_door
from .handlers.functions import price_functions
from .handlers.governance import price_governance
from .handlers.key_vault import price_key_vault
from .handlers.kubernetes import price_kubernetes
from .handlers.load_balancers import price_load_balancers
from .handlers.log_analytics import price_log_analytics
from .handlers.open_ai import price_open_ai
from .handlers.private_network import price_private_network
from .handlers.redis import price_redis
from .handlers.sql import price_sql
from .handlers.storage import price_storage
from .handlers.synapse import price_synapse
from .handlers.vm import price_vm

from .helpers.csv import arm_region
from .helpers.math import decimal, money
from .pricing.enterprise import (
    download_price_sheet_ea,
    download_price_sheet_mca,
    load_enterprise_csv,
    normalise_enterprise_rows,
)
from .pricing.retail import ensure_retail_cache, set_default_retail_csv
from .types import Key

log = logging.getLogger(__name__)


# ---------- Component prep helpers ----------

def _derive_quantity(component: Dict[str, Any]) -> Decimal:
    """
    Derive a neutral 'quantity' if not explicitly provided. This is UoM-agnostic.
    We look for common scale hints used across your BOMs.
    """
    if "quantity" in component:
        return decimal(component["quantity"])

    for k in (
            "instances", "vcores", "gateway_units", "capacity_units",
            "operations_per_month", "requests_per_month",
            "executions", "egress_gb", "gb", "tb", "tokens_1k", "images",
            "dwu", "clusters", "nodes", "calls_per_million", "requests_millions",
            "waf_policies", "waf_rules",
    ):
        if k in component:
            val = decimal(component[k])
            if k in ("requests_millions", "calls_per_million"):
                return val * decimal(1_000_000)
            if k == "tb":
                return val * decimal(1024)  # convert TB → GB
            return val

    return decimal(1)


def _apply_assumptions(component: Dict[str, Any], assumptions: Dict[str, Any]) -> None:
    if "hours_per_month" not in component:
        component["hours_per_month"] = assumptions.get("hours_per_month", 730)


def _prepare_component(component: Dict[str, Any], assumptions: Dict[str, Any]) -> Dict[str, Any]:
    c = dict(component)
    _apply_assumptions(c, assumptions)
    if "quantity" not in c:
        c["quantity"] = _derive_quantity(c)
    return c


def apply_optimisations(total: Decimal, assumptions: dict) -> Decimal:
    """
    Simple Savings Plan / Reserved Instance blending model.
    """
    sp_disc = decimal("0.18")  # assumed SP discount
    ri_disc = decimal("0.35")  # assumed RI discount
    sp_cov = decimal(assumptions.get("savings_plan", {}).get("coverage_pct", 0))
    ri_cov = decimal(assumptions.get("ri", {}).get("coverage_pct", 0))

    ri_slice   = total * ri_cov * (Decimal(1) - ri_disc)
    sp_slice   = total * (Decimal(1) - ri_cov) * sp_cov * (Decimal(1) - sp_disc)
    payg_slice = total * (Decimal(1) - ri_cov) * (Decimal(1) - sp_cov)
    return ri_slice + sp_slice + payg_slice


# ---------- Enterprise pricing helpers ----------

def _load_enterprise_prices(
        *,
        enterprise_price_sheet_api: Optional[str],
        billing_account: Optional[str],
        enrollment_account: Optional[str],
        aad_token: Optional[str],
        enterprise_csv: Optional[str],
) -> Dict[Key, Decimal]:
    """
    Try API (MCA/EA) first if configured, otherwise fall back to CSV, else empty.
    """
    ent_prices: Dict[Key, Decimal] = {}
    tried_enterprise = False

    try:
        if enterprise_price_sheet_api and aad_token:
            tried_enterprise = True
            if enterprise_price_sheet_api == "mca" and billing_account:
                log.info("Downloading MCA price sheet for billing account %s", billing_account)
                rows = download_price_sheet_mca(aad_token, billing_account)
                ent_prices = normalise_enterprise_rows(rows)
            elif enterprise_price_sheet_api == "ea" and enrollment_account:
                log.info("Downloading EA price sheet for enrollment account %s", enrollment_account)
                rows = download_price_sheet_ea(aad_token, enrollment_account)
                ent_prices = normalise_enterprise_rows(rows)

        if not ent_prices and enterprise_csv:
            tried_enterprise = True
            log.info("Loading enterprise prices from CSV: %s", enterprise_csv)
            ent_prices = load_enterprise_csv(enterprise_csv)

    except Exception as e:
        log.warning("Enterprise pricing failed, using retail only. Error: %s", e)

    if tried_enterprise and not ent_prices:
        log.info("No enterprise prices found (empty). Using retail only.")
    elif not tried_enterprise:
        log.info("Enterprise pricing not configured; using retail only.")

    return ent_prices


# ---------- Handler registry ----------

def _make_handlers(
        *,
        region: str,
        currency: str,
        ent_prices: Dict[Key, Decimal],
) -> Dict[str, Callable[[Dict[str, Any]], Tuple[Decimal, str]]]:
    """
    Build the map of component 'type' -> pricing function bound with region/currency/enterprise.
    """
    return {
        "open_ai":         lambda c: price_open_ai(c, region, currency, ent_prices),
        "kubernetes":      lambda c: price_kubernetes(c, region, currency, ent_prices),
        "api_management":  lambda c: price_api_management(c, region, currency, ent_prices),
        "app_insights":    lambda c: price_app_insights(c, region, currency, ent_prices),
        "app_service":     lambda c: price_app_service(c, region, currency, ent_prices),
        "egress":          lambda c: price_egress(c, region, currency, ent_prices),
        "backup":          lambda c: price_backup(c, region, currency, ent_prices),
        "cognitive_search":lambda c: price_cognitive_search(c, region, currency, ent_prices),
        "container_apps":  lambda c: price_container_apps(c, region, currency, ent_prices),
        "data_factory":    lambda c: price_data_factory(c, region, currency, ent_prices),
        "databricks":      lambda c: price_databricks(c, region, currency, ent_prices),
        "defender":        lambda c: price_defender(c, region, currency, ent_prices),
        "dev_ops":         lambda c: price_dev_ops(c, region, currency, ent_prices),
        "dns":             lambda c: price_dns(c, region, currency, ent_prices),
        "entra_id":        lambda c: price_entra_id(c, region, currency, ent_prices),
        "event_hubs":      lambda c: price_event_hubs(c, region, currency, ent_prices),
        "fabric":          lambda c: price_fabric(c, region, currency, ent_prices),
        "front_door":      lambda c: price_front_door(c, region, currency, ent_prices),
        "functions":       lambda c: price_functions(c, region, currency, ent_prices),
        "governance":      lambda c: price_governance(c, region, currency, ent_prices),
        "key_vault":       lambda c: price_key_vault(c, region, currency, ent_prices),
        "load_balancers":  lambda c: price_load_balancers(c, region, currency, ent_prices),
        "log_analytics":   lambda c: price_log_analytics(c, region, currency, ent_prices),
        "private_network": lambda c: price_private_network(c, region, currency, ent_prices),
        "redis":           lambda c: price_redis(c, region, currency, ent_prices),
        "sql":             lambda c: price_sql(c, region, currency, ent_prices),
        "storage":         lambda c: price_storage(c, region, currency, ent_prices),
        "synapse":         lambda c: price_synapse(c, region, currency, ent_prices),
        "vm":              lambda c: price_vm(c, region, currency, ent_prices),
    }


# ---------- Public entry point ----------

def run_model(
        *,
        bom: dict,
        currency_override: Optional[str],
        retail_csv: Optional[str],                 # local CSV fallback
        enterprise_csv: Optional[str],             # local CSV fallback
        enterprise_price_sheet_api: Optional[str], # "mca" | "ea" | None
        billing_account: Optional[str],            # for MCA
        enrollment_account: Optional[str],         # for EA
        aad_token: Optional[str],                  # token (if using enterprise_price_sheet_api); else None
) -> None:
    """
    Execute the pricing model:
      1) Optionally prepare a retail CSV cache
      2) Load enterprise prices (API or CSV)
      3) Price each workload's components with the correct region
      4) Apply simple SP/RI optimisation view
      5) Print summary totals
    """
    currency = currency_override or bom.get("currency", "AUD")
    assumptions = bom.get("assumptions", {})

    # Retail CSV cache (optional)
    if retail_csv:
        try:
            ensure_retail_cache(retail_csv, currency=currency)
            set_default_retail_csv(retail_csv)
            log.info("Using retail CSV cache: %s", retail_csv)
        except Exception as e:
            log.warning("Retail CSV setup failed (%s); falling back to live Retail API.", e)

    # Enterprise price map
    ent_prices = _load_enterprise_prices(
        enterprise_price_sheet_api=enterprise_price_sheet_api,
        billing_account=billing_account,
        enrollment_account=enrollment_account,
        aad_token=aad_token,
        enterprise_csv=enterprise_csv,
    )

    # Header
    print("\n=== Monthly Cost by Workload (Original vs With SP/RI modelling) ===")
    print(f"{'Workload':25} {'Tier':8} {'PAYG est.':>16} {'With Opt.':>16}")

    grand_total_opt = Decimal(0)

    # Iterate workloads
    for wl in bom.get("workloads", []):
        wl_name = wl.get("name", "(unnamed)")
        # Normalise human-readable region → ARM style (e.g., "Australia East" -> "australiaeast")
        wl_region = arm_region(wl.get("region", "Australia East"))
        handlers = _make_handlers(region=wl_region, currency=currency, ent_prices=ent_prices)

        wl_total = Decimal(0)
        print(f"\n-- {wl_name} components ({wl_region}) --")

        # Components
        for comp in wl.get("components", []):
            comp_type = comp.get("type", "")
            fn = handlers.get(comp_type)
            if fn is None:
                expected = ", ".join(sorted(handlers.keys()))
                log.warning("No handler for component type %r. Expected one of: %s", comp_type, expected)
                continue

            c = _prepare_component(comp, assumptions)
            try:
                cost, desc = fn(c)
            except Exception as e:
                log.warning("Pricing error for %s/%s: %s", wl_name, comp_type, e)
                cost, desc = Decimal(0), f"Error: {e}"

            wl_total += cost
            print(f"  • {comp_type:<18} {desc:<70} = ${cost:,.2f}")

        # Optimised view
        wl_total_opt = apply_optimisations(wl_total, assumptions)
        grand_total_opt += wl_total_opt

        print(
            f"{wl_name:25} {wl.get('tier','-'):8} "
            f"{('$'+format(wl_total, ',.2f')):>16} {('$'+format(wl_total_opt, ',.2f')):>16}"
        )

    # Footer
    print("\n=== Grand Total (Monthly, With Optimisations) ===")
    print(f"${money(grand_total_opt):,.2f} {currency}")