# azure-bill-of-materials-cost-calculator
BOM-driven Azure Cost Calculator (Enterprise + Retail)

## Before you start

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

```bash
pip install -e '.[dev]'
```

## What this gives you
- A single script that reads your **azure_bom.json**
- Prices using **Enterprise Price Sheet** (via API or a local CSV) when available
- Falls back to **Retail Prices API** for anything missing
- Prints **monthly per-workload totals** and **grand total**

## Files
src/azure_bom_costing/cli.py — entrypoint for the azure-bom CLI.
- src/azure_bom_costing/price_model.py — orchestrates BOM parsing, dispatches to handlers, applies SP/RI modelling, and prints results.
- src/azure_bom_costing/pricing_sources.py — retail (Prices API) + enterprise (MCA/EA/CSV) price retrieval, normalization, helpers.
- src/azure_bom_costing/helpers.py — shared helper utilities (decimals _d, _pick, _arm_region, text parsing, dedup, etc.).
- src/azure_bom_costing/types.py — shared type aliases (e.g., Key = Tuple[str, str, str, str]).
- src/azure_bom_costing/handlers/*.py — pure “BOM line → price” functions; each file focuses on one service area:
- examples/azure_bom.json — sample BOM with realistic components.
- examples/enterprise_prices.sample.csv — template CSV for enterprise prices (use if MCA/EA API isn’t configured yet).

## How to run

### Run (Retail only)
```
azure-bom --bom examples/azure_bom.json --retail-csv examples/retail_prices.sample.csv --currency AUD 
```

### Run with Enterprise API (MCA)
```
export AZ_TENANT_ID=...
export AZ_CLIENT_ID=...
export AZ_CLIENT_SECRET=...
azure-bom --enterprise-api mca --billing-account <BA_ID> --retail-csv examples/retail_prices.sample.csv --currency AUD
```

### Run with Enterprise API (EA)
```
export AZ_TENANT_ID=...
export AZ_CLIENT_ID=...
export AZ_CLIENT_SECRET=...
azure-bom --enterprise-api ea --enrollment_account <EA_ID> --retail-csv examples/retail_prices.sample.csv --currency AUD
```

### Run with Enterprise CSV (no API yet)
```
azure-bom --enterprise-csv examples/enterprise_prices.sample.csv --retail-csv examples/retail_prices.sample.csv --currency AUD
```

## Example

### Input

```json
{
  "region": "Australia East",
  "currency": "AUD",
  "assumptions": {
    "hours_per_month": 730,
    "fabric_workdays_per_month": 22,
    "savings_plan": { "term_years": 1, "coverage_pct": 0.6 },
    "ri": { "term_years": 3, "coverage_pct": 0.25 },
    "devtest_discount": false,
    "egress_gb_per_month": 500
  },
  "workloads": [
    {
      "name": "All-Services",
      "tier": "test",
      "components": [
        { "type": "open_ai",          "sku": "gpt-4o",                 "tokens_1k": 5000,      "hours_per_month": 1 },
        { "type": "kubernetes",       "sku": "Uptime SLA",             "clusters": 1,          "hours_per_month": 730 },
        { "type": "api_management",   "sku": "Developer",              "gateway_units": 1,     "hours_per_month": 730 },
        { "type": "app_insights",     "sku": "Ingest",                 "gb": 100,              "hours_per_month": 1 },
        { "type": "app_service",      "sku": "P1v4",                   "instances": 2,         "hours_per_month": 730 },
        { "type": "egress",           "sku": "Zone1 Internet",         "gb": 2000,             "hours_per_month": 1 },
        { "type": "backup",           "sku": "Protected Instance",     "quantity": 10,         "hours_per_month": 1 },
        { "type": "cognitive_search", "sku": "S1",                     "instances": 1,         "hours_per_month": 730 },
        { "type": "container_apps",   "sku": "Workload vCPU",          "instances": 2,         "hours_per_month": 730 },
        { "type": "data_factory",     "sku": "Pipeline Activity",      "quantity": 100000,     "hours_per_month": 1 },
        { "type": "databricks",       "sku": "DBU Premium",            "quantity": 2000,       "hours_per_month": 1 },
        { "type": "defender",         "sku": "Servers P2",             "quantity": 10,         "hours_per_month": 1 },
        { "type": "dev_ops",          "sku": "User Basic",             "quantity": 25,         "hours_per_month": 1 },
        { "type": "dns",              "sku": "DNS Queries",            "quantity": 100000000,  "hours_per_month": 1 },
        { "type": "entra_id",         "sku": "P1",                     "users": 1000,          "hours_per_month": 1 },
        { "type": "event_hubs",       "sku": "Standard",               "instances": 2,         "hours_per_month": 730 },
        { "type": "fabric",           "sku": "F64",                    "capacity_units": 64,   "hours_per_month": 730 },
        { "type": "front_door",       "sku": "Standard",               "requests_millions": 50, "egress_gb": 1000,  "hours_per_month": 730 },
        { "type": "functions",        "sku": "Executions",             "executions": 200000000, "hours_per_month": 1 },
        { "type": "governance",       "sku": "Policy Assessment",      "quantity": 1000000,    "hours_per_month": 1 },
        { "type": "key_vault",        "sku": "Premium",                "operations": 500000,   "hours_per_month": 1 },
        { "type": "load_balancers",   "sku": "Standard Rule Hour",     "instances": 2,         "hours_per_month": 730 },
        { "type": "log_analytics",    "sku": "Per GB",                 "gb": 500,              "hours_per_month": 1 },
        { "type": "private_network",  "sku": "Private Link",           "instances": 2,         "hours_per_month": 730 },
        { "type": "redis",            "sku": "C2",                     "instances": 1,         "hours_per_month": 730 },
        { "type": "sql",              "sku": "GP_S_Gen5_4",            "vcores": 4,            "hours_per_month": 730 },
        { "type": "storage",          "sku": "Standard LRS Hot",       "tb": 5, "transactions_per_month": 1000000 },
        { "type": "synapse",          "sku": "DW100c",                 "dwu": 100,             "hours_per_month": 730 },
        { "type": "vm",               "sku": "D2s_v5",                 "instances": 3,         "hours_per_month": 730 }
      ]
    }
  ]
}
```

### Output

```text
=== Monthly Cost by Workload (Original vs With SP/RI modelling) ===
Workload                  Tier            PAYG est.        With Opt.

-- All-Services components --
  • open_ai             Azure OpenAI gpt-4o @0/unit × 5000 × 1                                  = $0.00
  • kubernetes          Kubernetes Service Uptime SLA @0/unit × 1 × 730                         = $0.00
  • api_management      API Management Developer @0/unit × 1 × 730                              = $0.00
  • app_insights        Application Insights Ingest @0/unit × 100 × 1                           = $0.00
  • app_service         App Service P1v4 @0/unit × 2 × 730                                      = $0.00
  • egress              Bandwidth Zone1 Internet @0/unit × 2000 × 1                             = $0.00
  • backup              Backup Protected Instance @0/unit × 10 × 1                              = $0.00
  • cognitive_search    Cognitive Search S1 @0/unit × 1 × 730                                   = $0.00
  • container_apps      Container Apps Workload vCPU @0/unit × 2 × 730                          = $0.00
  • data_factory        Data Factory Pipeline Activity @0/unit × 100000 × 1                     = $0.00
  • databricks          Azure Databricks DBU Premium @0/unit × 2000 × 1                         = $0.00
  • defender            Microsoft Defender Servers P2 @0/unit × 10 × 1                          = $0.00
  • dev_ops             DevOps User Basic @0/unit × 25 × 1                                      = $0.00
  • dns                 DNS DNS Queries @0/unit × 100000000 × 1                                 = $0.00
  • entra_id            Microsoft Entra ID P1 @0/unit × 1 × 1                                   = $0.00
  • event_hubs          Event Hubs Standard @0/unit × 2 × 730                                   = $0.00
  • fabric              Microsoft Fabric F64 @0/unit × 64 × 730                                 = $0.00
  • front_door          Azure Front Door Standard @0/unit × 1000 × 730                          = $0.00
  • functions           Functions Executions @0/unit × 200000000 × 1                            = $0.00
  • governance          Governance Policy Assessment @0/unit × 1000000 × 1                      = $0.00
  • key_vault           Key Vault Premium @0/unit × 1 × 1                                       = $0.00
  • load_balancers      Load Balancer Standard Rule Hour @0/unit × 2 × 730                      = $0.00
  • log_analytics       Log Analytics Per GB @0/unit × 500 × 1                                  = $0.00
  • private_network     Virtual Network Private Link @0/unit × 2 × 730                          = $0.00
  • redis               Azure Cache for Redis C2 @0/1 Hour × 1 × 730                            = $0.00
  • sql                 Azure SQL Database GP_S_Gen5_4 @0/1 Hour × 4 × 730                      = $0.00
  • storage             Storage Standard LRS Hot @0/unit × 5120 × 730                           = $0.00
  • synapse             Azure Synapse Analytics DW100c @0/1 Hour × 100 × 730                    = $0.00
  • vm                  Virtual Machines D2s_v5 @0/1 Hour × 3 × 730                             = $0.00
All-Services              test                $0.00            $0.00

=== Grand Total (Monthly, With Optimisations) ===
$0.00 AUD
```

## Azure Pricing Field Reference (Retail + Enterprise Unified)

| **Field**              | **Example**                                   | **Source (CSV Column)**                    | **Description / Usage**                                                                                                                        |
|------------------------|-----------------------------------------------|--------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------|
| `serviceName`          | `"Virtual Machines"`                          | `serviceName` or `productName`             | The high-level Azure service family (e.g. Virtual Machines, Storage, SQL Database, App Service). Primary filter for service matching.          |
| `productName`          | `"Storage - Blob"`                            | `productName`                              | Descriptive product category under the service. Used for additional context when multiple product types exist (e.g. “File”, “Queue”, “Table”). |
| `skuName`              | `"Standard_D4s_v5"`, `"P1v4"`                 | `skuName`                                  | Specific SKU name identifying the performance or tier (e.g., VM size, App Service plan tier).                                                  |
| `armSkuName`           | `"Standard_D4s_v5"`                           | `armSkuName`                               | Normalised SKU for ARM APIs. Used when `skuName` is inconsistent across sources.                                                               |
| `meterName`            | `"Data Stored"`, `"Compute Hours"`            | `meterName`                                | Indicates what is being billed (e.g. “Compute Hours”, “Transactions”, “Data Stored”). Used by all handlers for targeted filtering.             |
| `meterId`              | `"b2a7c8e4-5fd3-4a47-b1a1-60ec1e1d3c0a"`      | `meterId`                                  | Unique Azure meter ID used for API-level lookups. Optional in CSV.                                                                             |
| `unitOfMeasure`        | `"1 Hour"`, `"1 GB/Month"`, `"10,000"`        | `unitOfMeasure`                            | The billing unit for that meter (e.g. per hour, per GB-month, per 10 000 transactions). Key for per-unit cost calculation.                     |
| `retailPrice`          | `0.125`                                       | `retailPrice`                              | Retail Pay-As-You-Go (PAYG) unit price for that meter. Expressed in the indicated `currencyCode`.                                              |
| `currencyCode`         | `"AUD"`                                       | `currencyCode`                             | Currency for the given price (e.g., AUD, USD, EUR). Determined by region.                                                                      |
| `priceType`            | `"Consumption"`, `"Reservation"`, `"DevTest"` | `priceType`                                | Indicates whether the row is standard PAYG, Reserved Instance, or Dev/Test pricing. All handlers default to `Consumption`.                     |
| `armRegionName`        | `"australiaeast"`                             | `armRegionName` or derived from `region`   | Azure-internal normalised region key (lowercase, no spaces). Used by `arm_region()` helper.                                                    |
| `region`               | `"Australia East"`                            | Derived / Display column                   | Human-readable Azure region label. In enterprise CSVs, may be blank (global).                                                                  |
| `location`             | `"Australia East"`                            | `location` (Retail CSV)                    | Alternate region column in Retail CSVs (used when `armRegionName` is missing).                                                                 |
| `serviceFamily`        | `"Compute"`, `"Storage"`, `"Databases"`       | `serviceFamily`                            | High-level service grouping (used to broaden search fallback when `serviceName` filtering fails).                                              |
| `productId`            | `"DZH318Z0BQCS"`                              | `productId`                                | Azure internal ID for the product. Used for correlation and debugging.                                                                         |
| `skuId`                | `"DZH318Z0BQCT"`                              | `skuId`                                    | Internal SKU identifier. May appear in enterprise sheets for EA/MCA billing alignment.                                                         |
| `effectiveStartDate`   | `"2024-10-01T00:00:00Z"`                      | `effectiveStartDate`                       | When this price became effective. Used to filter out expired prices.                                                                           |
| `effectiveEndDate`     | `null`                                        | `effectiveEndDate`                         | End of validity for this price. Null if still active.                                                                                          |
| `reservationTerm`      | `"1 Year"`, `"3 Years"`                       | `reservationTerm`                          | Used for reserved capacity and RI-based offers (not applied in on-demand pricing).                                                             |
| `isPrimaryMeterRegion` | `true`                                        | `isPrimaryMeterRegion`                     | Indicates whether this price is region-specific (true) or global (false). Handlers fall back to global when true is missing.                   |
| `type`                 | `"Consumption"`                               | `type`                                     | Duplicate of `priceType` in some CSVs. Normalised internally to `priceType`.                                                                   |
| `armSkuId`             | `"Standard_D4s_v5"`                           | Custom derived field                       | Computed from SKU where `armSkuName` missing.                                                                                                  |
| `tierMinimumUnits`     | `1`                                           | `tierMinimumUnits`                         | Minimum billing quantity per meter (e.g. per 10 000 transactions). Used for normalising “per count” metrics.                                   |
| `serviceId`            | `"DZH318Z0BQCS"`                              | `serviceId`                                | Unique ID for the service, internal Azure reference.                                                                                           |
| `offerId`              | `"MS-AZR-0003P"`                              | Enterprise CSV (EA/MCA)                    | Offer identifier from Enterprise Agreement or MCA. Used in enterprise lookups only.                                                            |
| `publisherId`          | `"Microsoft"`                                 | Enterprise CSV                             | Entity that publishes the meter (typically “Microsoft”).                                                                                       |
| `term`                 | `"1 Year"`                                    | Enterprise CSV                             | Reservation or Savings Plan term (when applicable).                                                                                            |
| `rate`                 | `0.09`                                        | Enterprise CSV                             | Unit rate (EA/MCA equivalent to `retailPrice`).                                                                                                |
| `uom`                  | `"1 Hour"`                                    | Enterprise CSV (`Unit Of Measure`)         | Enterprise equivalent of `unitOfMeasure`. Harmonised by handlers for consistency.                                                              |
| `regionName`           | `"Australia East"`                            | Enterprise CSV (`Region`)                  | Region column in EA/MCA sheets. May be empty for global SKUs.                                                                                  |
| `skuCategory`          | `"Compute"`, `"Storage"`, `"Networking"`      | Derived                                    | Inferred from `serviceFamily` or `productName` to group cost components.                                                                       |
| `pricingModel`         | `"Retail"`, `"Enterprise"`                    | Derived                                    | Indicates whether the price originated from Retail or Enterprise sheet.                                                                        |
| `quantity`             | `2`, `1000`, `1048576`                        | Derived from BOM (`instances`, `tb`, etc.) | Runtime-only field computed in `run_model` for unified per-component quantity input.                                                           |