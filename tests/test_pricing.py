from decimal import Decimal

from azure_bom_costing.price_model import _normalise_downloaded
from azure_bom_costing.pricing.enterprise import enterprise_lookup
from azure_bom_costing.pricing.retail import _parse_simple_filter


def _matches(filter_expr: str, row: dict[str, str]) -> bool:
    return all(pred(row) for pred in _parse_simple_filter(filter_expr))


def test_simple_filter_binds_each_clause_independently() -> None:
    expr = "serviceName eq 'Key Vault' and contains(skuName, 'standard')"
    assert _matches(expr, {"serviceName": "key vault", "skuName": "Premium Standard"})
    assert not _matches(expr, {"serviceName": "Key Vault", "skuName": "Premium"})
    assert not _matches(expr, {"serviceName": "Storage", "skuName": "Standard"})


def test_enterprise_lookup_handles_missing_service_or_sku() -> None:
    ent = {("Key Vault", "Standard", "", "1"): Decimal("1.5")}
    assert enterprise_lookup(ent, "Key Vault", "Standard", "australiaeast", "1") == Decimal("1.5")
    assert enterprise_lookup(ent, None, "Standard", "australiaeast", "1") is None
    assert enterprise_lookup(ent, "Key Vault", None, "australiaeast", "1") is None


def test_normalise_downloaded_ignores_unrecognised_json() -> None:
    rows = [{"serviceName": "VM", "skuName": "D2", "armRegionName": "x", "unitOfMeasure": "1 Hour",
             "unitPrice": "0.2"}]
    assert _normalise_downloaded(rows) == {("VM", "D2", "x", "1 Hour"): Decimal("0.2")}
    assert _normalise_downloaded({"properties": {}}) == {}
