# azure-bill-of-materials-cost-calculator
BOM-driven Azure Cost Calculator (Enterprise + Retail)

## Before you start

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
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

### Run (Retail only) - AVAILABLE
```
azure-bom --bom examples/azure_bom.json --retail-offline --currency AUD 
```

### Run with Enterprise API (MCA) - COMING LATER
```
export AZ_TENANT_ID=...
export AZ_CLIENT_ID=...
export AZ_CLIENT_SECRET=...
azure-bom --enterprise-price-sheet-api mca --billing-account <BA_ID> --retail-csv examples/retail_prices.sample.csv --currency AUD
```

### Run with Enterprise API (EA) - COMING LATER
```
export AZ_TENANT_ID=...
export AZ_CLIENT_ID=...
export AZ_CLIENT_SECRET=...
azure-bom --enterprise-price-sheet-api ea --enrollment_account <EA_ID> --retail-csv examples/retail_prices.sample.csv --currency AUD
```

### Run with Enterprise & Retail CSV (no API yet) - COMING LATER
```
azure-bom --enterprise-csv examples/enterprise_prices.sample.csv --retail-csv examples/retail_prices.sample.csv --currency AUD
```

## Example

### Input

```json
{
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
      "name": "All-Services-AE",
      "region": "Australia East",
      "tier": "prod",
      "components": [
        { "type": "app_service",      "service": "Azure App Service",             "sku": "P1v3",                     "instances": 3, "hours_per_month": 730, "purpose": "Client & Partner Portals, ShareDo extensions" },
        { "type": "functions",        "service": "Functions",               "sku": "Consumption",               "executions": 0,                   "hours_per_month": 1,   "purpose": "API & event-driven logic" },
        { "type": "kubernetes",       "service": "Kubernetes Service",      "sku": "Uptime SLA",                "clusters": 1,  "hours_per_month": 730, "purpose": "Modernised LPS modules (containers)" },
        { "type": "container_apps",   "service": "Container Apps",          "sku": "Standard",                  "instances": 2, "hours_per_month": 730, "purpose": "Background processing / lightweight jobs" },
        { "type": "vm",               "service": "Virtual Machines",        "sku": "Standard_D2_v5",            "instances": 2, "hours_per_month": 730, "purpose": "Legacy lift-and-shift apps" },

        { "type": "dns",              "service": "DNS",                      "sku": "Zones",                     "zones": 1,     "queries": 0,           "hours_per_month": 730, "purpose": "Public/Private DNS" },
        { "type": "private_network",  "service": "Virtual Network",          "sku": "Private Link",              "instances": 4, "hours_per_month": 730, "purpose": "Private connectivity to PaaS" },
        { "type": "vpn_gateway",      "service": "VPN Gateway",              "sku": "VpnGw2",                    "instances": 1, "hours_per_month": 730, "purpose": "Hybrid connectivity" },
        { "type": "front_door",       "service": "Azure Front Door",         "sku": "Standard+WAF",              "requests_millions": 0, "egress_gb": 0, "hours_per_month": 730, "purpose": "External access & web protection" },
        { "type": "expressroute",     "service": "ExpressRoute",             "sku": "1Gbps",                     "circuits": 1,  "hours_per_month": 730, "purpose": "Private link to on-prem datacentre" },

        { "type": "defender",         "service": "Microsoft Defender",       "sku": "Defender for Cloud",        "resources": 1, "hours_per_month": 730, "purpose": "Threat protection" },
        { "type": "sentinel",         "service": "Microsoft Sentinel",       "sku": "PayGo",                     "gb": 0,        "hours_per_month": 1,   "purpose": "SIEM & central logging" },
        { "type": "key_vault",        "service": "Key Vault",                "sku": "Standard",                  "operations": 0,"hours_per_month": 1,   "purpose": "Secrets, certificates, keys" },

        { "type": "fabric",           "service": "Microsoft Fabric",         "sku": "F64",                       "capacity_units": 64, "hours_per_month": 730, "purpose": "Data Lakehouse + Power BI capacity" },
        { "type": "sql",              "service": "SQL Database",             "sku": "BusinessCritical_8_vCore",  "vcores": 8,    "hours_per_month": 730, "purpose": "ShareDo, Portal & Finance databases" },
        { "type": "data_factory",     "service": "Data Factory",             "sku": "Pipeline Activity",         "quantity": 0,  "hours_per_month": 1,   "purpose": "ETL & integration pipelines" },
        { "type": "storage",          "service": "Storage (Blob)",           "sku": "Hot",                       "tb": 5,        "transactions_per_month": 0, "purpose": "Documents (iManage, ShareDo)" },
        { "type": "storage",          "service": "Data Lake Gen2",           "sku": "Cool",                      "tb": 1,        "transactions_per_month": 0, "purpose": "Analytics & AI data" },

        { "type": "open_ai",          "service": "Cognitive Services",       "sku": "gpt-4o",                    "tokens_1k": 0, "hours_per_month": 1,   "purpose": "Triage, chat, client insight" },
        { "type": "cognitive_search", "service": "Cognitive Search",         "sku": "S1",                        "instances": 1, "hours_per_month": 730, "purpose": "Document indexing & search" },

        { "type": "service_bus",      "service": "Service Bus",              "sku": "Premium P1",                "instances": 2, "hours_per_month": 730, "purpose": "Reliable messaging between systems" },
        { "type": "event_grid",       "service": "Event Grid",               "sku": "Standard",                  "events": 0,    "hours_per_month": 1,   "purpose": "Event-driven orchestration" },
        { "type": "logic_apps",       "service": "Logic Apps",               "sku": "Standard",                  "executions": 0,"hours_per_month": 1,   "purpose": "Salesforce/DocuSign workflows" },

        { "type": "app_insights",     "service": "Application Insights",     "sku": "Ingest",                    "gb": 0,        "hours_per_month": 1,   "purpose": "App telemetry" },
        { "type": "log_analytics",    "service": "Log Analytics",            "sku": "Per GB",                    "gb": 0,        "hours_per_month": 1,   "purpose": "Logs & metrics" },
        { "type": "automation",       "service": "Automation",               "sku": "Jobs",                      "quantity": 0,  "hours_per_month": 1,   "purpose": "Runbooks & patching" },

        { "type": "storage",          "service": "Archive Storage",          "sku": "Archive",                   "tb": 1,        "transactions_per_month": 0, "purpose": "Long-term retention" },
        { "type": "backup",           "service": "Backup",                   "sku": "Protected Instance",        "quantity": 1,  "hours_per_month": 1,   "purpose": "Backup of VMs/SQL/storage" },
        { "type": "site_recovery",    "service": "Site Recovery",            "sku": "Standard",                  "protected_vms": 1, "hours_per_month": 730, "purpose": "DR replication" }
      ]
    },
    {
      "name": "All-Services-ASE",
      "region": "Australia South East",
      "tier": "prod",
      "components": [
        { "type": "app_service",      "service": "Azure App Service",             "sku": "P1v3",           "instances": 0, "hours_per_month": 730, "purpose": "Regional capacity (Melbourne) — set if active/active" },
        { "type": "kubernetes",       "service": "Kubernetes Service",      "sku": "Uptime SLA",    "clusters": 0,  "hours_per_month": 730, "purpose": "Secondary region (if required)" },
        { "type": "front_door",       "service": "Azure Front Door",        "sku": "Standard+WAF",  "requests_millions": 0, "egress_gb": 0, "hours_per_month": 730, "purpose": "Global entry — same policy applies" },
        { "type": "expressroute",     "service": "ExpressRoute",            "sku": "1Gbps",         "circuits": 0,  "hours_per_month": 730, "purpose": "Secondary circuit if dual-home" },
        { "type": "storage",          "service": "Storage (Blob)",          "sku": "Hot",           "tb": 0,        "transactions_per_month": 0, "purpose": "Geo-redundant data (optional)" }
      ]
    }
  ]
}
```

### Output

```text

```

## Azure Pricing Field Reference (Retail + Enterprise Unified)
