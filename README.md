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
- `price_model.py` — main script
- `handlers.py` → pure “BOM line → price” logic, works for retail and enterprise
- `azure_bom.json` — sample BOM
- `enterprise_prices.sample.csv` — a template for enterprise prices (if you don't have API access yet)

## Run (Retail only)
```
azure-bom --bom azure_bom.json --currency AUD
```

## Run with Enterprise API (MCA)
```
export AZ_TENANT_ID=...
export AZ_CLIENT_ID=...
export AZ_CLIENT_SECRET=...
azure-bom --enterprise-api mca --billing-account <BA_ID> --currency AUD
```

## Run with Enterprise CSV (no API yet)
```
azure-bom --enterprise-csv examples/enterprise_prices.sample.csv --bom examples/azure_bom.json --currency AUD
```

## Notes
- The script normalises enterprise rows to keys: `(serviceName, skuName, region, unitOfMeasure)`
- Matching is heuristic; keep your CSV column names like the sample for best results
- Optimisations (Savings Plan/RI) are simple sliders — replace with your real discounts later
