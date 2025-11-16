# Azure Bill of Materials Cost Calculator
BOM‑driven Azure Cost Calculator (Enterprise + Retail + Offline Retail JSON)

---

## 🚀 What This Tool Does

This cost calculator ingests a **BOM (Bill of Materials)** describing your Azure workloads and produces:

- 🔹 **Monthly PAYG cost estimate**
- 🔹 **SP/RI‑optimised monthly cost**
- 🔹 Fully automated pricing from:
    - **Enterprise Price Sheet API (MCA/EA)**
    - **Enterprise CSV price sheets**
    - **Retail Prices API**
    - **Retail Offline JSON (download once → super fast afterwards)**

---

## 📦 Installation

```bash
python3 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e '.[dev]'
```

---

## ⚙️ New Features

### ✅ **Retail JSON Offline Mode**
You can now download the full Azure Retail pricing pages to disk:

```
examples/temp/retail-prices-XXXX.json
```

After this, your model runs:

✔️ Offline  
✔️ Faster  
✔️ Reproducibly  
✔️ Without hitting the API

---

## 🧪 How To Run

---

### **1) Retail Offline Mode (downloads JSON pages)**

```bash
azure-bom --bom examples/azure_bom.json           --retail-offline           --currency AUD
```

Optional flags:

```bash
--retail-temp-dir examples/temp
--retail-filter "serviceName eq 'Virtual Machines'"
```

---

### **2) Retail Only (live API)**

```bash
azure-bom --bom examples/azure_bom.json --currency AUD
```

---

### **3) Enterprise Price Sheet API – MCA**

```bash
export AZ_TENANT_ID=...
export AZ_CLIENT_ID=...
export AZ_CLIENT_SECRET=...

azure-bom --bom examples/azure_bom.json           --enterprise-price-sheet-api mca           --billing-account <BA_ID>           --currency AUD
```

---

### **4) Enterprise Price Sheet API – EA**

```bash
export AZ_TENANT_ID=...
export AZ_CLIENT_ID=...
export AZ_CLIENT_SECRET=...

azure-bom --bom examples/azure_bom.json           --enterprise-price-sheet-api ea           --enrollment-account <EA_ID>           --currency AUD
```

---

### **5) Enterprise CSV + Retail Offline JSON**

```bash
azure-bom --bom examples/azure_bom.json           --enterprise-csv examples/enterprise_prices.csv           --retail-offline           --currency AUD
```

---

## 📘 BOM Structure - Important Fields

Top‑level BOM fields:

```json
{
  "currency": "AUD",
  "assumptions": {
    "hours_per_month": 730,
    "savings_plan": { "coverage_pct": 0.60 },
    "ri": { "coverage_pct": 0.25 }
  },
  "retail_offline": true,
  "retail_filter": "serviceName eq 'Azure App Service'",
  "retail_temp_dir": "examples/temp",
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

---

## 📊 Output Example

```
=== Monthly Cost by Workload (Original vs With SP/RI modelling) ===
Workload                  Tier        PAYG est.       With Opt.

-- All-Services-AE components (australiaeast) --
  • app_service         Azure App Service P1v4 @0.45977/unit × 3 × 730 = $1,006.90
  ...
All-Services-AE         prod          $4,520.92         $3,100.14

=== Grand Total (Monthly, With Optimisations) ===
$3,850.44 AUD
```

---

## 🧾 Azure Pricing Source Summary

| Source                              | Used When                                               | Notes                              |
|-------------------------------------|---------------------------------------------------------|------------------------------------|
| Enterprise Price Sheet API (MCA/EA) | If configured                                           | Matches Azure Calculator pricing   |
| Enterprise CSV                      | API disabled or unavailable                             | Must be exported from Azure Portal |
| Retail Offline JSON                 | If `--retail-offline` or BOM sets `retail_offline=true` | Fast, repeatable                   |
| Retail Live API                     | Default fallback                                        | Public list pricing                |

---

## ⚠️ Matching Azure Pricing Calculator

Azure Retail API returns **public retail list price**, not your contract rate.

Azure Pricing Calculator uses **your MCA/EA discounted contract price**.

To match it exactly, run with:

```
--enterprise-price-sheet-api mca --billing-account <BA_ID>
```

---

## 📂 Project Structure

```
src/azure_bom_costing/
  cli.py               # CLI entrypoint
  price_model.py       # Main orchestration + handlers
  pricing/
    retail.py          # Offline + live Retail API
    enterprise.py      # MCA/EA API + CSV
  handlers/            # Per-service pricing logic
  helpers/             # decimals, filters, region mapping
examples/
  azure_bom.json
  enterprise_prices.sample.csv
  temp/
```
