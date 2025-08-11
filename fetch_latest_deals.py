#!/usr/bin/env python3
"""
Fetch Year-To-Date HubSpot deals (excluding closedwon/closedlost) and export to CSV.

Columns:
- deal: Deal name
- value: Amount
- dealstage: Deal stage (internal name)
- dealowner: Owner full name or email
- expiration_date: Close date
- created_at_date: Create date
- customer_name: First associated contact's full name
- company_name: First associated company's name

Filters:
- createdate >= start of current year (UTC)
- dealstage not in [closedwon, closedlost]

Auth:
- Use environment variable HUBSPOT_TOKEN or the --token flag.

Usage examples:
  # Fetch ALL YTD deals (default)
  HUBSPOT_TOKEN=xxxxx python3 fetch_latest_deals.py
  
  # Fetch first 200 YTD deals
  python3 fetch_latest_deals.py --token xxxxx --limit 200 --output latest_deals.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone

import requests


HUBSPOT_BASE_URL = "https://api.hubapi.com"


class HubSpotClient:
    def __init__(self, token: str, timeout_seconds: float = 20.0) -> None:
        self.token = token
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )
        self.timeout_seconds = timeout_seconds

    def _handle_response(self, response: requests.Response) -> dict:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:  # pragma: no cover
            # Avoid printing token in any error
            message = (
                f"HubSpot API error {response.status_code} for {response.request.method} {response.url}: "
                f"{response.text}"
            )
            raise SystemExit(message) from exc
        try:
            return response.json()
        except ValueError:  # pragma: no cover
            raise SystemExit("Unexpected non-JSON response from HubSpot API")

    def post(self, path: str, json: dict) -> dict:
        url = f"{HUBSPOT_BASE_URL}{path}"
        resp = self.session.post(url, json=json, timeout=self.timeout_seconds)
        return self._handle_response(resp)

    def get(self, path: str, params: Optional[dict] = None) -> dict:
        url = f"{HUBSPOT_BASE_URL}{path}"
        resp = self.session.get(url, params=params, timeout=self.timeout_seconds)
        return self._handle_response(resp)


def safe_format_date(iso_str: Optional[str]) -> str:
    if not iso_str:
        return ""
    # Expect values like 2023-07-03T17:41:04.193Z or 2023-07-03T17:41:04Z
    from datetime import datetime

    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(iso_str, fmt)
            return dt.date().isoformat()
        except ValueError:
            continue
    return iso_str  # fallback without transformation


def fetch_ytd_deals_excluding_closed(
    client: HubSpotClient, limit: int
) -> List[dict]:
    """Use the Search API to get YTD deals excluding closedwon/closedlost, sorted by createdate DESC."""
    current_year = datetime.now(timezone.utc).year
    start_of_year = datetime(current_year, 1, 1, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {
        "limit": limit,
        "properties": [
            "dealname",
            "amount",
            "dealstage",
            "closedate",
            "createdate",
            "hubspot_owner_id",
        ],
        "filterGroups": [
            {
                # AND within group
                "filters": [
                    {"propertyName": "createdate", "operator": "GTE", "value": start_of_year},
                    {"propertyName": "dealstage", "operator": "NEQ", "value": "closedwon"},
                    {"propertyName": "dealstage", "operator": "NEQ", "value": "closedlost"},
                ]
            }
        ],
        "sorts": [
            {"propertyName": "createdate", "direction": "DESCENDING"}
        ],
    }
    data = client.post("/crm/v3/objects/deals/search", json=body)
    return data.get("results", [])


def fetch_ytd_deals_excluding_closed_all(client: HubSpotClient) -> List[dict]:
    """Fetch all YTD deals excluding closedwon/closedlost by paginating the Search API."""
    current_year = datetime.now(timezone.utc).year
    start_of_year = datetime(current_year, 1, 1, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    page_limit = 100
    after: Optional[str] = None
    all_results: List[dict] = []

    while True:
        body = {
            "limit": page_limit,
            "properties": [
                "dealname",
                "amount",
                "dealstage",
                "closedate",
                "createdate",
                "hubspot_owner_id",
            ],
            "filterGroups": [
                {
                    "filters": [
                        {"propertyName": "createdate", "operator": "GTE", "value": start_of_year},
                        {"propertyName": "dealstage", "operator": "NEQ", "value": "closedwon"},
                        {"propertyName": "dealstage", "operator": "NEQ", "value": "closedlost"},
                    ]
                }
            ],
            "sorts": [
                {"propertyName": "createdate", "direction": "DESCENDING"}
            ],
        }
        if after:
            body["after"] = after

        data = client.post("/crm/v3/objects/deals/search", json=body)
        results = data.get("results", [])
        all_results.extend(results)
        after = (data.get("paging", {}) or {}).get("next", {}).get("after")
        if not after:
            break

    return all_results


def fetch_owner_lookup(client: HubSpotClient) -> Dict[str, str]:
    """Return mapping from owner id to a human-friendly name."""
    owners: Dict[str, str] = {}
    after: Optional[str] = None
    while True:
        params = {"archived": "false"}
        if after:
            params["after"] = after
        data = client.get("/crm/v3/owners/", params=params)
        for item in data.get("results", []):
            owner_id = str(item.get("id") or "")
            first = item.get("firstName") or ""
            last = item.get("lastName") or ""
            email = item.get("email") or ""
            name = (f"{first} {last}".strip()) or email or owner_id
            if owner_id:
                owners[owner_id] = name
            # Backwards compatibility keys sometimes observed
            if item.get("ownerId"):
                owners[str(item["ownerId"])] = name
        after = (data.get("paging", {}) or {}).get("next", {}).get("after")
        if not after:
            break
    return owners


def resolve_owner_name(client: HubSpotClient, owner_id: Optional[str], owners: Dict[str, str]) -> str:
    if not owner_id:
        return ""
    if owner_id in owners:
        return owners[owner_id]
    # Fallback: look up owner by HUBSPOT_OWNER_ID
    try:
        data = client.get(f"/crm/v3/owners/{owner_id}", params={"idProperty": "HUBSPOT_OWNER_ID"})
        first = data.get("firstName") or ""
        last = data.get("lastName") or ""
        email = data.get("email") or ""
        name = (f"{first} {last}".strip()) or email or owner_id
        owners[owner_id] = name
        return name
    except SystemExit:
        return owner_id


def fetch_association_ids(
    client: HubSpotClient, deal_id: str, to_object: str
) -> List[str]:
    data = client.get(f"/crm/v3/objects/deals/{deal_id}/associations/{to_object}")
    ids: List[str] = []
    for r in data.get("results", []):
        # v3 often returns "id" for the associated object id
        if "id" in r:
            ids.append(str(r["id"]))
        elif "toObjectId" in r:  # legacy shape
            ids.append(str(r["toObjectId"]))
    return ids


def batch_read_objects(
    client: HubSpotClient, object_type: str, ids: List[str], properties: List[str]
) -> Dict[str, dict]:
    if not ids:
        return {}
    unique_ids = list(dict.fromkeys(ids))  # preserve order, ensure uniqueness
    result: Dict[str, dict] = {}
    # HubSpot batch read typically supports up to 100 inputs per call
    chunk_size = 100
    for i in range(0, len(unique_ids), chunk_size):
        chunk = unique_ids[i : i + chunk_size]
        body = {"properties": properties, "inputs": [{"id": x} for x in chunk]}
        data = client.post(f"/crm/v3/objects/{object_type}/batch/read", json=body)
        for item in data.get("results", []):
            obj_id = str(item.get("id"))
            result[obj_id] = item.get("properties", {})
    return result


def build_csv_rows(
    client: HubSpotClient, deals: List[dict]
) -> Tuple[List[str], List[List[str]]]:
    header = [
        "deal",
        "value",
        "dealstage",
        "dealowner",
        "expiration_date",
        "created_at_date",
        "customer_name",
        "company_name",
    ]

    owners = fetch_owner_lookup(client)

    # Collect association ids
    all_contact_ids: List[str] = []
    all_company_ids: List[str] = []
    deal_to_first_contact: Dict[str, Optional[str]] = {}
    deal_to_first_company: Dict[str, Optional[str]] = {}

    for d in deals:
        deal_id = str(d.get("id"))
        contact_ids = fetch_association_ids(client, deal_id, "contacts")
        company_ids = fetch_association_ids(client, deal_id, "companies")
        deal_to_first_contact[deal_id] = contact_ids[0] if contact_ids else None
        deal_to_first_company[deal_id] = company_ids[0] if company_ids else None
        all_contact_ids.extend(contact_ids)
        all_company_ids.extend(company_ids)

    contacts = batch_read_objects(
        client, "contacts", all_contact_ids, ["firstname", "lastname", "email"]
    )
    companies = batch_read_objects(
        client, "companies", all_company_ids, ["name", "domain"]
    )

    rows: List[List[str]] = []
    for d in deals:
        props = d.get("properties", {})
        deal_id = str(d.get("id"))
        deal_name = props.get("dealname") or ""
        amount = props.get("amount") or ""
        stage = props.get("dealstage") or ""
        owner_id = props.get("hubspot_owner_id") or ""
        owner_name = resolve_owner_name(client, str(owner_id) if owner_id else None, owners)
        closedate = safe_format_date(props.get("closedate"))
        createdate = safe_format_date(props.get("createdate"))

        contact_id = deal_to_first_contact.get(deal_id)
        contact_props = contacts.get(contact_id or "", {})
        first = contact_props.get("firstname") or ""
        last = contact_props.get("lastname") or ""
        customer_name = (f"{first} {last}".strip()) or contact_props.get("email") or ""

        company_id = deal_to_first_company.get(deal_id)
        company_props = companies.get(company_id or "", {})
        company_name = company_props.get("name") or ""

        rows.append(
            [
                deal_name,
                amount,
                stage,
                owner_name,
                closedate,
                createdate,
                customer_name,
                company_name,
            ]
        )

    return header, rows


def write_csv(path: str, header: List[str], rows: List[List[str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export YTD HubSpot deals (excluding closedwon/closedlost) to CSV")
    parser.add_argument("--token", default=os.getenv("HUBSPOT_TOKEN"), help="HubSpot Private App token")
    parser.add_argument("--limit", type=int, default=0, help="Number of YTD deals to fetch (0 = all)")
    parser.add_argument(
        "--output",
        default="latest_deals.csv",
        help="Output CSV file path (default latest_deals.csv)",
    )
    args = parser.parse_args()

    if not args.token:
        print("Missing token. Provide --token or set HUBSPOT_TOKEN.", file=sys.stderr)
        sys.exit(2)

    client = HubSpotClient(args.token)
    if args.limit and args.limit > 0:
        deals = fetch_ytd_deals_excluding_closed(client, args.limit)
    else:
        deals = fetch_ytd_deals_excluding_closed_all(client)
    header, rows = build_csv_rows(client, deals)
    write_csv(args.output, header, rows)
    print(f"Wrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()


