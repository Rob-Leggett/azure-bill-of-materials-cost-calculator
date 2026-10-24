# Azure Bill of Materials Cost Calculator

[![CI](https://github.com/Rob-Leggett/azure-bill-of-materials-cost-calculator/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Rob-Leggett/azure-bill-of-materials-cost-calculator/actions/workflows/ci.yml) [![Python 3.13](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)

BOM-driven Azure Cost Calculator supporting both **Standard** (Retail API) and **Enterprise** (MCA/EA) pricing tiers.

---

## 🚀 What This Tool Does

This cost calculator ingests a **BOM (Bill of Materials)** describing your Azure workloads and produces:

- 🔹 **Monthly PAYG cost estimate**
- 🔹 **SP/RI-optimised monthly cost**
- 🔹 Fully automated pricing from:
    - **Standard Pricing** – Azure Retail Prices API (public list pricing)
    - **Enterprise Pricing** – MCA/EA Price Sheet API or CSV (contract rates)
    - **Offline Mode** – Download retail prices once for fast, reproducible runs

---

## 📦 Installation

Requires **Python 3.13+** and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                       # creates .venv and installs the app + dev tools from uv.lock
source .venv/bin/activate     # Windows: .venv\Scripts\activate (or prefix commands with `uv run`)
```

---

## 🧪 Usage

### Quick Start

```bash
# Standard pricing (Retail API)
azure-bom --bom examples/azure_bom.json --pricing-tier standard --currency AUD

# Enterprise pricing (requires MCA/EA credentials)
azure-bom --bom examples/azure_bom.json --pricing-tier enterprise \
    --enterprise-price-sheet-api mca --billing-account <BA_ID> --currency AUD
```

### Pricing Tiers

| Tier | Description | Use Case |
|------|-------------|----------|
| `standard` | Uses Azure Retail Prices API (public list pricing) | General estimates, no Azure contract |
| `enterprise` | Uses MCA/EA price sheets (contract rates) | Match Azure Pricing Calculator exactly |

---

### **1) Standard Pricing (default)**

Uses the public Azure Retail Prices API:

```bash
azure-bom --bom examples/azure_bom.json --currency AUD
```

With offline mode (download prices once, run offline afterwards):

```bash
azure-bom --bom examples/azure_bom.json --retail-offline --currency AUD
```

Optional flags:

```bash
--retail-temp-dir examples/retail    # Directory to store cached prices
--retail-filter "serviceName eq 'Virtual Machines'"  # Filter API results
```

---

### **2) Enterprise Pricing – MCA**

Uses your Microsoft Customer Agreement contract rates:

```bash
export AZ_TENANT_ID=...
export AZ_CLIENT_ID=...
export AZ_CLIENT_SECRET=...

azure-bom --bom examples/azure_bom.json \
    --pricing-tier enterprise \
    --enterprise-price-sheet-api mca \
    --billing-account <BA_ID> \
    --currency AUD
```

---

### **3) Enterprise Pricing – EA**

Uses your Enterprise Agreement contract rates:

```bash
export AZ_TENANT_ID=...
export AZ_CLIENT_ID=...
export AZ_CLIENT_SECRET=...

azure-bom --bom examples/azure_bom.json \
    --pricing-tier enterprise \
    --enterprise-price-sheet-api ea \
    --enrollment-account <EA_ID> \
    --currency AUD
```

---

### **4) Enterprise CSV + Retail Fallback**

Use a manually exported enterprise price sheet with retail fallback:

```bash
azure-bom --bom examples/azure_bom.json \
    --pricing-tier enterprise \
    --enterprise-csv examples/enterprise_prices.csv \
    --retail-offline \
    --currency AUD
```

---

## 📘 BOM Structure

Top-level BOM fields:

```json
{
  "currency": "AUD",
  "assumptions": {
    "hours_per_month": 730,
    "savings_plan": { "coverage_pct": 0.60 },
    "ri": { "coverage_pct": 0.25 }
  },
  "retail_offline": true,
  "retail_temp_dir": "examples/retail",
  "workloads": [{
      "name": "All-Services-AE",
      "region": "Australia East",
      "tier": "prod",
      "components": [...]
    }]
}
```

Component example:

```json
{
  "type": "app_service",
  "service": "Azure App Service",
  "sku": "P1v4",
  "instances": 3,
  "hours_per_month": 730
}
```

### Supported Component Types

| Type | Service |
|------|---------|
| `api_management` | Azure API Management |
| `app_insights` | Application Insights |
| `app_service` | Azure App Service |
| `automation` | Azure Automation |
| `backup` | Azure Backup |
| `cognitive_search` | Azure Cognitive Search |
| `container_apps` | Azure Container Apps |
| `data_factory` | Azure Data Factory |
| `databricks` | Azure Databricks |
| `defender` | Microsoft Defender for Cloud |
| `dev_ops` | Azure DevOps |
| `dns` | Azure DNS |
| `egress` | Data Transfer/Egress |
| `entra_id` | Microsoft Entra ID |
| `event_grid` | Azure Event Grid |
| `event_hubs` | Azure Event Hubs |
| `expressroute` | Azure ExpressRoute |
| `fabric` | Microsoft Fabric |
| `front_door` | Azure Front Door |
| `functions` | Azure Functions |
| `governance` | Azure Governance |
| `key_vault` | Azure Key Vault |
| `kubernetes` | Azure Kubernetes Service |
| `load_balancers` | Azure Load Balancer |
| `log_analytics` | Azure Log Analytics |
| `logic_apps` | Azure Logic Apps |
| `open_ai` | Azure OpenAI Service |
| `private_network` | Virtual Network / Private Link |
| `redis` | Azure Cache for Redis |
| `sentinel` | Microsoft Sentinel |
| `service_bus` | Azure Service Bus |
| `site_recovery` | Azure Site Recovery |
| `sql` | Azure SQL Database |
| `storage` | Azure Storage |
| `synapse` | Azure Synapse Analytics |
| `vm` | Azure Virtual Machines |
| `vpn_gateway` | Azure VPN Gateway |

---

## 📊 Output Example

```
=== Azure BOM Cost Calculator (STANDARD pricing) ===

=== Monthly Cost by Workload (Original vs With SP/RI modelling) ===
Workload                  Tier            PAYG est.        With Opt.

-- All-Services-AE components (australiaeast) --
  • app_service        Azure App Service P1v4 @0.45977/unit × 3 × 730 = $1,006.90
  • vm                 Virtual Machines Standard_D2_v5 @0.036/unit × 2 × 730 = $53.00
  ...
All-Services-AE           prod           $4,520.92       $3,100.14

=== Grand Total (Monthly, With Optimisations) ===
$3,100.14 AUD
```

---

## 🧾 Pricing Source Summary

| Pricing Tier | Source | Notes |
|--------------|--------|-------|
| `standard` | Retail Prices API | Public list pricing |
| `standard` + `--retail-offline` | Cached JSON files | Fast, offline, reproducible |
| `enterprise` | MCA/EA Price Sheet API | Your contract rates |
| `enterprise` + `--enterprise-csv` | Exported CSV | Manual fallback |

---

## ⚠️ Matching Azure Pricing Calculator

The Azure Pricing Calculator uses **your MCA/EA contract rates**, not public list prices.

To match it exactly, use enterprise pricing:

```bash
azure-bom --pricing-tier enterprise \
    --enterprise-price-sheet-api mca \
    --billing-account <BA_ID>
```

---

## 📂 Project Structure

```
src/azure_bom_costing/
  cli.py               # CLI entrypoint
  price_model.py       # Main orchestration
  pricing/
    retail.py          # Offline + live Retail API
    enterprise.py      # MCA/EA API + CSV
  handlers/            # Per-service pricing logic (37 services)
  helpers/             # Math, CSV, HTTP, pricing utilities
examples/
  azure_bom.json       # Sample BOM file
  retail/              # Cached retail price pages
```

---

## 🛠️ Development

```bash
# Install app + dev dependencies
uv sync

# Run linter
uv run ruff check .

# Run type checker
uv run mypy src tests

# Run tests
uv run pytest

# Audit dependencies for known vulnerabilities
uv run pip-audit

# Upgrade all dependencies to their latest versions
uv lock --upgrade && uv sync
```
