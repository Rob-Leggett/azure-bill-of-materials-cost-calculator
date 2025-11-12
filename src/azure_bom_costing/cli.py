from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Optional

from .helpers.auth import get_aad_token
from .price_model import run_model


# ---------- Logging ----------

def enable_logging(level: int = logging.INFO) -> None:
    """Configure root logger with a simple, useful format."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )


# ---------- CLI ----------

def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="azure-bom",
        description="Azure BOM Costing Tool: builds a monthly cost estimate from a BOM.",
    )

    ap.add_argument(
        "--bom",
        default="examples/azure_bom.json",
        help="Path to the input BOM JSON file (default: examples/azure_bom.json)",
    )
    ap.add_argument(
        "--currency",
        default="AUD",
        help="3-letter currency code, e.g. AUD, USD (default: AUD)",
    )
    ap.add_argument(
        "--retail-csv",
        help="Path to a retail prices CSV cache (optional, used for offline/fast lookups).",
    )
    ap.add_argument(
        "--enterprise-csv",
        help="Path to an Enterprise price sheet CSV (optional, used if API is not set or fails).",
    )
    ap.add_argument(
        "--enterprise-price-sheet-api",
        choices=["mca", "ea"],
        help="Use Enterprise Price Sheet API (MCA or EA). Requires Azure credentials via env vars.",
    )
    ap.add_argument(
        "--billing-account",
        help="Billing Account ID for MCA (required if --enterprise-price-sheet-api mca).",
    )
    ap.add_argument(
        "--enrollment-account",
        help="Enrollment Account ID for EA (required if --enterprise-price-sheet-api ea).",
    )
    return ap.parse_args()


def _load_bom(path: Path) -> dict:
    if not path.exists():
        logging.error("BOM file not found: %s", path)
        raise SystemExit(2)
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error("Failed to read BOM JSON (%s): %s", path, e)
        raise SystemExit(2)


def _maybe_get_aad_token(api_choice: Optional[str]) -> Optional[str]:
    """
    Retrieve an AAD token if the enterprise price sheet API is requested and
    the standard env vars are present. Logs helpful messages if anything is missing.
    """
    if not api_choice:
        logging.info("Enterprise pricing API not configured; using retail/CSV only.")
        return None

    missing = [k for k in ("AZ_TENANT_ID", "AZ_CLIENT_ID", "AZ_CLIENT_SECRET") if not os.getenv(k)]
    if missing:
        logging.warning(
            "Missing env vars for enterprise API (%s). Will skip API and fall back to CSV/retail.",
            ", ".join(missing),
        )
        return None

    try:
        token = get_aad_token(
            os.getenv("AZ_TENANT_ID"),
            os.getenv("AZ_CLIENT_ID"),
            os.getenv("AZ_CLIENT_SECRET"),
        )
        logging.info("Obtained AAD token for enterprise price sheet API: %s", api_choice.upper())
        return token
    except Exception as e:
        logging.warning("Failed to obtain AAD token (%s). Falling back to CSV/retail. Error: %s", api_choice, e)
        return None


def _validate_enterprise_api_args(api_choice: Optional[str], billing_account: Optional[str], enrollment_account: Optional[str]) -> None:
    """
    Ensure the right account id is present for the chosen enterprise API type.
    """
    if not api_choice:
        return

    if api_choice == "mca" and not billing_account:
        logging.error("You specified --enterprise-price-sheet-api mca, but no --billing-account was provided.")
        raise SystemExit(2)
    if api_choice == "ea" and not enrollment_account:
        logging.error("You specified --enterprise-price-sheet-api ea, but no --enrollment-account was provided.")
        raise SystemExit(2)


def main() -> None:
    args = _parse_args()

    bom_path = Path(args.bom).expanduser().resolve()
    bom = _load_bom(bom_path)

    # Validate enterprise API arguments early
    _validate_enterprise_api_args(
        args.enterprise_price_sheet_api,
        args.billing_account,
        args.enrollment_account,
    )

    # Acquire token if API was requested and env is present
    token = _maybe_get_aad_token(args.enterprise_price_sheet_api)

    # Run the model
    run_model(
        bom=bom,
        currency_override=args.currency,
        enterprise_price_sheet_api=args.enterprise_price_sheet_api,
        billing_account=args.billing_account,
        enrollment_account=args.enrollment_account,
        retail_csv=args.retail_csv,
        enterprise_csv=args.enterprise_csv,
        aad_token=token,
    )


if __name__ == "__main__":
    enable_logging()
    main()