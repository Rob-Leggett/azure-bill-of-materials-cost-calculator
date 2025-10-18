from __future__ import annotations
import argparse
import json
import os
import pathlib

from .price_model import run_model
from .pricing_sources import get_aad_token


def main() -> None:
    ap = argparse.ArgumentParser(prog="azure-bom", description="Azure BOM Costing")
    ap.add_argument("--bom", default="examples/azure_bom.json", help="Path to BOM JSON")
    ap.add_argument("--currency", default=None, help="Currency code (e.g. AUD)")
    ap.add_argument("--enterprise-api", choices=["mca", "ea"], help="Use Enterprise Price Sheet API")
    ap.add_argument("--billing-account", help="Billing Account Id (MCA)")
    ap.add_argument("--enrollment-account", help="Enrolment Account Id (EA)")
    ap.add_argument("--enterprise-csv", help="Path to enterprise prices CSV (optional)")
    args = ap.parse_args()

    bom_path = pathlib.Path(args.bom).expanduser().resolve()
    if not bom_path.exists():
        print(f"[ERROR] BOM file not found: {bom_path}")
        raise SystemExit(2)
    with open(bom_path, "r", encoding="utf-8") as f:
        bom = json.load(f)

    token = None
    if args.enterprise_api:
        missing = [k for k in ("AZ_TENANT_ID", "AZ_CLIENT_ID", "AZ_CLIENT_SECRET") if not os.getenv(k)]
        if missing:
            print(f"[WARN] Missing env vars for enterprise API: {', '.join(missing)}")
        else:
            token = get_aad_token(
                os.getenv("AZ_TENANT_ID"),
                os.getenv("AZ_CLIENT_ID"),
                os.getenv("AZ_CLIENT_SECRET")
            )

    run_model(
        bom=bom,
        currency_override=args.currency,
        enterprise_api=args.enterprise_api,
        billing_account=args.billing_account,
        enrollment_account=args.enrollment_account,
        enterprise_csv=args.enterprise_csv,
        aad_token=token,
    )


if __name__ == "__main__":
    main()