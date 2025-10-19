from __future__ import annotations
from decimal import Decimal
from typing import Dict, Optional

from .handlers.api_management import price_api_management
from .handlers.app_insights import price_app_insights
from .handlers.app_service import price_app_service
from .handlers.backup import price_backup
from .handlers.cognitive_search import price_cognitive_search
from .handlers.container_apps import price_container_apps
from .handlers.data_bricks import price_databricks
from .handlers.data_factory import price_data_factory
from .handlers.defender import price_defender
from .handlers.dev_ops import price_devops
from .handlers.dns import price_dns_tm
from .handlers.event_hubs import price_service_bus, price_event_hub, price_event_grid
from .handlers.front_door import price_front_door
from .handlers.functions import price_functions
from .handlers.goverance import price_governance
from .handlers.key_vault import price_key_vault
from .handlers.kubernetes import price_aks_cluster
from .handlers.load_balancers import price_app_gateway, price_load_balancer
from .handlers.private_network import price_private_networking
from .handlers.redis import price_redis
from .handlers.storage import price_blob_storage, price_storage_queue, price_storage_table, price_fileshare
from .handlers.egress import price_bandwidth
from .handlers.entra_id import price_entra_external_id
from .handlers.fabric import price_fabric_capacity, price_onelake_storage
from .handlers.log_analytics import price_log_analytics
from .handlers.open_ai import price_ai_openai
from .handlers.sql import price_sql_paas
from .handlers.synapse import price_synapse_sqlpool
from .handlers.vm import price_vm
from .helpers import _d
from .pricing_sources import (
    download_price_sheet_mca, download_price_sheet_ea,
    normalise_enterprise_rows, load_enterprise_csv,
    money,
)
from .types import Key


def apply_optimisations(total: Decimal, assumptions: dict) -> Decimal:
    """Simple Savings Plan / RI model. Tune as you like."""
    sp_disc = _d("0.18")
    ri_disc = _d("0.35")
    sp_cov = _d(assumptions.get("savings_plan", {}).get("coverage_pct", 0))
    ri_cov = _d(assumptions.get("ri", {}).get("coverage_pct", 0))
    ri_slice   = total * ri_cov * (Decimal(1) - ri_disc)
    sp_slice   = total * (Decimal(1) - ri_cov) * sp_cov * (Decimal(1) - sp_disc)
    payg_slice = total * (Decimal(1) - ri_cov) * (Decimal(1) - sp_cov)
    return ri_slice + sp_slice + payg_slice


def run_model(
        bom: dict,
        currency_override: Optional[str],
        enterprise_api: Optional[str],          # "mca" | "ea" | None
        billing_account: Optional[str],         # for MCA
        enrollment_account: Optional[str],      # for EA
        enterprise_csv: Optional[str],          # local CSV fallback
        aad_token: Optional[str],               # token (if using enterprise_api); else None
) -> None:
    region = bom["region"]
    currency = currency_override or bom.get("currency", "AUD")
    assumptions = bom.get("assumptions", {})

    # Load enterprise prices (API or CSV)
    ent_prices: Dict[Key, Decimal] = {}
    try:
        if enterprise_api and aad_token:
            if enterprise_api == "mca" and billing_account:
                rows = download_price_sheet_mca(aad_token, billing_account)
                ent_prices = normalise_enterprise_rows(rows)
            elif enterprise_api == "ea" and enrollment_account:
                rows = download_price_sheet_ea(aad_token, enrollment_account)
                ent_prices = normalise_enterprise_rows(rows)
        if not ent_prices and enterprise_csv:
            ent_prices = load_enterprise_csv(enterprise_csv)
    except Exception as e:
        print(f"[WARN] Enterprise pricing not loaded: {e}. Using retail only.")

    # Dispatch
    handlers = {
        "ai_openai":            lambda c: price_ai_openai(c, region, currency, ent_prices),
        "aks_cluster":          lambda c: price_aks_cluster(c, region, currency, ent_prices),
        "api_management":       lambda c: price_api_management(c, region, currency, ent_prices),
        "app_gateway":          lambda c: price_app_gateway(c, region, currency, ent_prices),
        "app_insights":         lambda c: price_app_insights(c, region, currency, ent_prices),
        "app_service":          lambda c: price_app_service(c, region, currency, ent_prices),
        "bandwidth_egress":     lambda c: price_bandwidth(c, region, currency, ent_prices),
        "backup":               lambda c: price_backup(c, region, currency, ent_prices),
        "cognitive_search":     lambda c: price_cognitive_search(c, region, currency, ent_prices),
        "container_apps":       lambda c: price_container_apps(c, region, currency, ent_prices),
        "data_factory":         lambda c: price_data_factory(c, region, currency, ent_prices),
        "databricks":           lambda c: price_databricks(c, region, currency, ent_prices),
        "defender":             lambda c: price_defender(c, region, currency, ent_prices),
        "devops":               lambda c: price_devops(c, region, currency, ent_prices),
        "dns_tm":               lambda c: price_dns_tm(c, region, currency, ent_prices),
        "entra_external_id":    lambda c: price_entra_external_id(c, region, currency, ent_prices),
        "event_grid":           lambda c: price_event_grid(c, region, currency, ent_prices),
        "event_hub":            lambda c: price_event_hub(c, region, currency, ent_prices),
        "fabric_capacity":      lambda c: price_fabric_capacity(c, region, currency, ent_prices),
        "fileshare":            lambda c: price_fileshare(c, region, currency, ent_prices),
        "front_door":           lambda c: price_front_door(c, region, currency, ent_prices),
        "functions":            lambda c: price_functions(c, region, currency, ent_prices),
        "governance":           lambda c: price_governance(c, region, currency, ent_prices),
        "key_vault":            lambda c: price_key_vault(c, region, currency, ent_prices),
        "load_balancer":        lambda c: price_load_balancer(c, region, currency, ent_prices),
        "log_analytics":        lambda c: price_log_analytics(c, region, currency, ent_prices),
        "onelake_storage":      lambda c: price_onelake_storage(c, region, currency, ent_prices),
        "private_networking":   lambda c: price_private_networking(c, region, currency, ent_prices),
        "redis":                lambda c: price_redis(c, region, currency, ent_prices),
        "service_bus":          lambda c: price_service_bus(c, region, currency, ent_prices),
        "sql_paas":             lambda c: price_sql_paas(c, region, currency, ent_prices),
        "storage_blob":         lambda c: price_blob_storage(c, region, currency, ent_prices),
        "storage_queue":        lambda c: price_storage_queue(c, region, currency, ent_prices),
        "storage_table":        lambda c: price_storage_table(c, region, currency, ent_prices),
        "synapse_sqlpool":      lambda c: price_synapse_sqlpool(c, region, currency, ent_prices),
        "vm":                   lambda c: price_vm(c, region, currency, ent_prices),
    }

    grand_total_opt = Decimal(0)

    print("\n=== Monthly Cost by Workload (Original vs With SP/RI modelling) ===")
    print(f"{'Workload':25} {'Tier':8} {'PAYG est.':>16} {'With Opt.':>16}")

    for wl in bom.get("workloads", []):
        wl_total = Decimal(0)
        print(f"\n-- {wl.get('name','(unnamed)')} components --")
        for comp in wl.get("components", []):
            t = comp.get("type")
            fn = handlers.get(t)
            if not fn:
                print(f"[WARN] No handler for component type: {t}")
                continue
            cost, desc = fn(comp)                       # keep desc
            wl_total += cost
            print(f"  • {t:<18}  {desc:<70}  = ${cost:,.2f}")

        wl_total_opt = apply_optimisations(wl_total, assumptions)
        grand_total_opt += wl_total_opt

        print(f"{wl.get('name','(unnamed)'):25} {wl.get('tier','-'):8} "
              f"{('$'+format(wl_total, ',.2f')):>16} {('$'+format(wl_total_opt, ',.2f')):>16}")

    print("\n=== Grand Total (Monthly, With Optimisations) ===")
    print(f"${money(grand_total_opt):,.2f} {currency}")