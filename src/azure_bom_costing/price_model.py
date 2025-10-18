from __future__ import annotations
from decimal import Decimal
from typing import Dict, Tuple, Optional

from .handlers import (
    price_vm, price_app_service, price_sql_paas,
    price_storage, price_bandwidth, price_fabric_capacity,
    price_onelake_storage,
)
from .pricing_sources import (
    download_price_sheet_mca, download_price_sheet_ea,
    normalise_enterprise_rows, load_enterprise_csv,
    money, d,
)

Key = Tuple[str, str, str, str]  # (serviceName, skuName, region, unitOfMeasure)


def apply_optimisations(total: Decimal, assumptions: dict) -> Decimal:
    """Simple Savings Plan / RI model. Tune as you like."""
    sp_disc = d("0.18")
    ri_disc = d("0.35")
    sp_cov = d(assumptions.get("savings_plan", {}).get("coverage_pct", 0))
    ri_cov = d(assumptions.get("ri", {}).get("coverage_pct", 0))
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
        "vm":               lambda c: price_vm(c, region, currency, ent_prices),
        "app_service":      lambda c: price_app_service(c, region, currency, ent_prices),
        "sql_paas":         lambda c: price_sql_paas(c, region, currency, ent_prices),
        "storage":          lambda c: price_storage(c, region, currency, ent_prices),
        "bandwidth_egress": lambda c: price_bandwidth(c, region, currency, ent_prices),
        "fabric_capacity":  lambda c: price_fabric_capacity(c, region, currency, ent_prices),
        "onelake_storage":  lambda c: price_onelake_storage(c, region, currency, ent_prices),
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