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
azure-bom --bom examples/azure_bom.json --currency AUD
```

### Run with Enterprise API (MCA)
```
export AZ_TENANT_ID=...
export AZ_CLIENT_ID=...
export AZ_CLIENT_SECRET=...
azure-bom --enterprise-api mca --billing-account <BA_ID> --currency AUD
```

### Run with Enterprise CSV (no API yet)
```
azure-bom --enterprise-csv examples/enterprise_prices.sample.csv --bom examples/azure_bom.json --currency AUD
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
      "name": "PartnerPortal",
      "tier": "prod",
      "components": [
        { "type": "app_service", "sku": "P1v3", "instances": 2, "hours_per_month": 730 },
        { "type": "storage_blob", "sku": "Standard_LRS_Hot", "tb": 1, "transactions_per_month": 300000 },
        { "type": "front_door", "tier": "Standard", "hours_per_month": 730, "requests_millions": 200, "egress_gb": 1000, "waf_policies": 1, "waf_rules": 10 },
        { "type": "api_management", "tier": "Standard", "gateway_units": 2, "hours_per_month": 730, "calls_per_million": 50 },
        { "type": "redis", "sku": "C2", "instances": 1, "hours_per_month": 730 },
        { "type": "key_vault", "tier": "Premium", "operations": 500000, "hsm_keys": 5 }
      ]
    },
    {
      "name": "Identity",
      "tier": "shared",
      "components": [
        { "type": "entra_external_id", "monthly_active_users": 50000, "mfa_enabled_pct": 0.9, "premium_features": true }
      ]
    },
    {
      "name": "AI",
      "tier": "prod",
      "components": [
        { "type": "ai_openai", "deployment": "gpt-4o-mini", "input_tokens_1k_per_month": 18000, "output_tokens_1k_per_month": 9000, "images_generated": 0, "embeddings_tokens_1k_per_month": 0 }
      ]
    },
    {
      "name": "DataPlatform",
      "tier": "prod",
      "components": [
        { "type": "fabric_capacity", "sku": "F64", "hours_per_day": 16, "days_per_month": 22 },
        { "type": "onelake_storage", "tb_hot": 10, "tb_cool": 40 },
        { "type": "synapse_sqlpool", "sku": "DW1000c", "hours_per_month": 200 },
        { "type": "databricks", "tier": "Premium", "dbu_hours": 500 },
        { "type": "data_factory", "diu_hours": 200, "activity_runs_1k": 50 },
        { "type": "event_hub", "tier": "Standard", "throughput_units": 4, "hours_per_month": 730 },
        { "type": "service_bus", "tier": "Premium", "messaging_units": 2, "hours_per_month": 730 },
        { "type": "event_grid", "operations_per_month": 200000000 }
      ]
    },
    {
      "name": "Reporting",
      "tier": "prod",
      "components": [
        { "type": "fabric_capacity", "sku": "F32", "hours_per_day": 12, "days_per_month": 22 },
        { "type": "cognitive_search", "sku": "S1", "replicas": 2, "partitions": 1, "hours_per_month": 730 }
      ]
    },
    {
      "name": "Observability",
      "tier": "shared",
      "components": [
        { "type": "log_analytics", "ingest_gb_per_day": 120, "retention_days": 30 },
        { "type": "app_insights", "ingest_gb_per_day": 10, "retention_days": 30, "days_per_month": 30, "included_retention_days": 0 },
        { "type": "defender", "plan": "Servers", "resource_count": 20, "hours_per_month": 730 }
      ]
    },
    {
      "name": "LogsArchive",
      "tier": "shared",
      "components": [
        { "type": "storage_blob", "sku": "Standard_LRS_Cool", "tb": 4, "transactions_per_month": 400000 },
        { "type": "backup", "backup_storage_tb": 2, "redundancy": "LRS", "instances_small": 5, "instances_medium": 2 }
      ]
    },
    {
      "name": "Networking",
      "tier": "shared",
      "components": [
        { "type": "bandwidth_egress", "gb_per_month": 1800 },
        { "type": "private_networking", "private_endpoints": 6, "pe_hours": 730, "nat_gateways": 2, "nat_hours": 730, "nat_data_gb": 1500 },
        { "type": "load_balancer", "sku": "Standard", "data_processed_gb": 800, "rules": 5, "hours_per_month": 730 },
        { "type": "app_gateway", "capacity_units": 2, "data_processed_gb": 500, "hours_per_month": 730 },
        { "type": "dns_tm", "dns_zones": 5, "dns_queries_millions": 30, "tm_profiles": 2, "tm_queries_millions": 20, "hours_per_month": 730 }
      ]
    },
    {
      "name": "AKS_And_Backend",
      "tier": "prod",
      "components": [
        { "type": "aks_cluster", "uptime_sla": true, "hours_per_month": 730 },
        { "type": "vm", "armSku": "Standard_D4s_v5", "count": 3, "os": "Linux", "hours_per_month": 730 },
        { "type": "sql_paas", "sku": "GP_P_Gen5_8", "max_gb": 512, "ha": true }
      ]
    },
    {
      "name": "IntegrationAndQueues",
      "tier": "shared",
      "components": [
        { "type": "functions", "gb_seconds": 250000000, "executions": 200000000 },
        { "type": "storage_queue", "operations_per_month": 120000000 },
        { "type": "storage_table", "operations_per_month": 80000000 },
        { "type": "fileshare", "tb": 3 }
      ]
    },
    {
      "name": "PlatformGovernance",
      "tier": "shared",
      "components": [
        { "type": "governance" }
      ]
    }
  ]
}
```

### Output

```text
=== Monthly Cost by Workload (Original vs With SP/RI modelling) ===
Workload                  Tier            PAYG est.        With Opt.

-- PartnerPortal components --
  • app_service         AppService P1v3 x2 @ 5.399771/hr                                        = $7,883.67
  • storage_blob        Storage Standard_LRS_Hot 1TB @ 0.030569/GB-mo (+tx)                     = $31.64
  • front_door          Front Door Standard (base+req+egress+WAF)                               = $0.00
  • api_management      APIM Standard 2x @ 0.523454/hr × 730h + 50M req @ 0/1M                  = $764.24
  • redis               Redis C2 x1 @ 0/hr × 730h                                               = $0.00
  • key_vault           Key Vault Premium (ops+keys)                                            = $2.29
PartnerPortal             prod            $8,681.84        $7,218.95

-- Identity components --
  • entra_external_id   Entra External ID base:50000 @ 0/MAU mfa:90% @ 0/MAU (premium)          = $0.00
Identity                  shared              $0.00            $0.00

-- AI components --
  • ai_openai           OpenAI in:18000k @ 0.000252/1k out:9000k @ 0.001009/1k                  = $13.62
AI                        prod               $13.62           $11.32

-- DataPlatform components --
  • fabric_capacity     Fabric F64 @ 15.484906/hr × 16h × 22d                                   = $5,450.69
  • onelake_storage     OneLake Hot:10TB Cool:40TB                                              = $1,001.69
  • synapse_sqlpool     Synapse SQLPool DW1000c @ 258.311043/DWU-hr × 1000 DWU × 200h           = $51,662,208.60
  • databricks          Databricks Premium @ 0.22927/DBU-hr × 500h                              = $114.64
  • data_factory        Data Factory (DIU:200h, Activities:50k)                                 = $0.00
  • event_hub           Event Hubs Standard TU @ 0.045854/hr × 4 × 730h                         = $133.89
  • service_bus         Service Bus Premium MU @ 1.417654/hr × 2 × 730h                         = $2,069.77
  • event_grid          Event Grid 200000000 ops @ 0.091708/1M                                  = $18.34
DataPlatform              prod       $51,670,997.62   $42,964,434.52

-- Reporting components --
  • fabric_capacity     Fabric F32 @ 0.775638/hr × 12h × 22d                                    = $204.77
  • cognitive_search    Cog Search S1 SU:2 @ 0/hr × 730h                                        = $0.00
Reporting                 prod              $204.77          $170.26

-- Observability components --
  • log_analytics       LogAnalytics ingest:3600GB @ 0.106993/GB                                = $385.17
  • app_insights        App Insights ingest:10GB/d @ 0/GB + retention 30d                       = $45.85
  • defender            Defender Servers 20x @ 0.010271/hr × 730h                               = $149.96
Observability             shared            $580.99          $483.09

-- LogsArchive components --
  • storage_blob        Storage Standard_LRS_Cool 4TB @ 0.016813/GB-mo (+tx)                    = $69.31
  • backup              Azure Backup (storage + protected instances)                            = $0.00
LogsArchive               shared             $69.31           $57.63

-- Networking components --
  • bandwidth_egress    Egress 1800GB @ 0.146733/GB (Bandwidth - Routing Preference: Internet / Standard Data Transfer Out)  = $264.12
  • private_networking  Private Networking (PE + NAT)                                           = $0.00
  • load_balancer       Load Balancer Standard (data:800GB, rules:5 × 730h)                     = $0.00
  • app_gateway         App Gateway v2 (CU:2 × 730h, data:500GB)                                = $23.97
  • dns_tm              DNS + Traffic Manager                                                   = $16.51
Networking                shared            $304.59          $253.27

-- AKS_And_Backend components --
  • aks_cluster         AKS Uptime SLA @ 0.152847/hr × 730h                                     = $111.58
  • vm                  VM Standard_D4s_v5 x3 @ 0.64807/hr                                      = $1,419.27
  • sql_paas            SQL GP_P_Gen5_8 @ 22.149087/vCore-hr × 8 vC (+storage approx)           = $194,026.00
AKS_And_Backend           prod          $195,556.85      $162,605.52

-- IntegrationAndQueues components --
  • functions           Functions (GB-s + execs)                                                = $0.02
  • storage_queue       Queue ops:120000000 @ 0.006114/10k                                      = $73.37
  • storage_table       Table ops:80000000 @ 0.198701/10k                                       = $1,589.61
  • fileshare           File share 3TB @ 0.04295/GB-mo                                          = $131.94
IntegrationAndQueues      shared          $1,794.93        $1,492.49

-- PlatformGovernance components --
  • governance          Governance (Policy/Advisor/Blueprints typically $0)                     = $0.00
PlatformGovernance        shared              $0.00            $0.00

=== Grand Total (Monthly, With Optimisations) ===
$43,136,727.06 AUD
```

## Notes
- The script normalises enterprise rows to keys: `(serviceName, skuName, region, unitOfMeasure)`
- Matching is heuristic; keep your CSV column names like the sample for best results
- Optimisations (Savings Plan/RI) are simple sliders — replace with your real discounts later

## Terminology

| **Field**           | **Example**                                  | **Source**                                          | **Description**                                                                                                      |
|---------------------|----------------------------------------------|-----------------------------------------------------|----------------------------------------------------------------------------------------------------------------------|
| `serviceName`       | `"Virtual Machines"`                         | `productName` or `serviceName` in Azure price sheet | High-level Azure service family (e.g., Virtual Machines, Storage, SQL Database, App Service). Used to narrow lookup. |
| `skuName`           | `"Standard_D4s_v5"`                          | `skuName` or `armSkuName`                           | Specific SKU for that service (e.g., VM size, App Service plan tier, Fabric capacity).                               |
| `region`            | `"Australia East"`                           | `armRegionName` or `location`                       | The Azure region that the price applies to. Some enterprise sheets leave this blank for global meters.               |
| `unitOfMeasure`     | `"1 Hour"`, `"1 GB/Month"`, `"10,000"`, etc. | `unitOfMeasure`                                     | The billing unit for that SKU — per hour, per GB-month, per 10 000 transactions, etc.                                |

