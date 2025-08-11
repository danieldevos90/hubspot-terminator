#!/usr/bin/env python3
"""
Aggregate deals by owner from a deals CSV.

Outputs summary_by_owner.csv with columns:
- owner: owner name
- deals_count: number of deals
- total_value: sum of numeric values (non-numeric/blank treated as 0)
- companies_count: number of unique companies
- companies: sorted, semicolon-separated list of unique company names

Usage:
  python3 report_by_owner.py --input latest_deals.csv --output summary_by_owner.csv
"""

from __future__ import annotations

import argparse
import csv
from typing import Dict, List, Set


def parse_float(value: str) -> float:
    if value is None:
        return 0.0
    s = str(value).strip()
    if not s:
        return 0.0
    # Allow commas in thousands or decimal, attempt best effort
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize deals per owner from a CSV")
    parser.add_argument("--input", default="latest_deals.csv", help="Path to input CSV (default latest_deals.csv)")
    parser.add_argument("--output", default="summary_by_owner.csv", help="Path to output CSV (default summary_by_owner.csv)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    with open(args.input, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    owner_to_deal_count: Dict[str, int] = {}
    owner_to_total_value: Dict[str, float] = {}
    owner_to_companies: Dict[str, Set[str]] = {}

    for r in rows:
        owner = (r.get("dealowner") or "").strip() or "(unknown)"
        value = parse_float(r.get("value"))
        company = (r.get("company_name") or "").strip()

        owner_to_deal_count[owner] = owner_to_deal_count.get(owner, 0) + 1
        owner_to_total_value[owner] = owner_to_total_value.get(owner, 0.0) + value
        if owner not in owner_to_companies:
            owner_to_companies[owner] = set()
        if company:
            owner_to_companies[owner].add(company)

    summary_rows: List[dict] = []
    for owner in sorted(owner_to_deal_count.keys()):
        companies = sorted(owner_to_companies.get(owner, set()))
        summary_rows.append(
            {
                "owner": owner,
                "deals_count": owner_to_deal_count[owner],
                "total_value": f"{owner_to_total_value[owner]:.2f}",
                "companies_count": len(companies),
                "companies": "; ".join(companies),
            }
        )

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "owner",
                "deals_count",
                "total_value",
                "companies_count",
                "companies",
            ],
        )
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"Wrote {len(summary_rows)} rows to {args.output}")


if __name__ == "__main__":
    main()


