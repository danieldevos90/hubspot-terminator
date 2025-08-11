# HubSpot Terminator

Utility scripts to export and analyze HubSpot deals via the CRM v3 API.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Export deals (YTD, excluding closedwon/closedlost)

```bash
# Option A: use environment
export HUBSPOT_TOKEN='YOUR_PRIVATE_APP_TOKEN'

# Option B: create a .env file (dotenv is loaded automatically)
echo "HUBSPOT_TOKEN=YOUR_PRIVATE_APP_TOKEN" > .env

python3 fetch_latest_deals.py --output latest_deals.csv    # all YTD
# or limit results
python3 fetch_latest_deals.py --limit 200 --output latest_deals.csv
```

CSV columns: `deal, value, dealstage, dealowner, expiration_date, created_at_date, customer_name, company_name`.

## Reports

- Missing values and companies affected:

```bash
python3 report_missing_deals.py --input latest_deals.csv --output deals_missing.csv
```

- Per owner summary (deals count, total value, unique companies):

```bash
python3 report_by_owner.py --input latest_deals.csv --output summary_by_owner.csv
```

## Reference
- HubSpot CRM Deals API: https://developers.hubspot.com/docs/reference/api/crm/objects/deals
