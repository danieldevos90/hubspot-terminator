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

## SharePoint (Microsoft Graph)

This repo includes `sharepoint_read_files.py` to list or download files from SharePoint using Microsoft Graph with application permissions.

Environment (in `.env.local` or via `--env`):
- `AZURE_TENANT_ID`: Azure AD tenant ID
- `AZURE_CLIENT_ID`: App registration (client) ID
- `AZURE_CLIENT_SECRET`: Client secret for the app registration

Your app must have admin-consented application permissions such as `Files.Read.All` or `Sites.Read.All`.

Examples:

```bash
# List root of the Documents library on a site
python3 sharepoint_read_files.py --env .env.local \
  --site-host contoso.sharepoint.com --site-path /sites/Sales --list /

# List a folder
python3 sharepoint_read_files.py --env .env.local \
  --site-host contoso.sharepoint.com --site-path /sites/Sales \
  --list "/Shared Reports/2025"

# Download a specific file
python3 sharepoint_read_files.py --env .env.local \
  --site-host contoso.sharepoint.com --site-path /sites/Sales \
  --download "/Shared Reports/2025/summary.xlsx" --out ./summary.xlsx

# Download a folder recursively
python3 sharepoint_read_files.py --env .env.local \
  --site-host contoso.sharepoint.com --site-path /sites/Sales \
  --download-folder "/Shared Reports/2025" --out-dir ./downloads
```
