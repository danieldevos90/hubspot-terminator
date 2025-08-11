#!/usr/bin/env python3
"""
Report rows with missing values in a deals CSV and list affected company names.

Input CSV is expected to be like the output of fetch_latest_deals.py
with headers including: deal, value, dealstage, dealowner, expiration_date,
created_at_date, customer_name, company_name.

Usage:
  python3 report_missing_deals.py \
    --input latest_deals.csv \
    --output deals_missing.csv \
    --columns deal,value,dealstage,dealowner,expiration_date,created_at_date,customer_name,company_name

If --columns is omitted, all columns present in the CSV are checked.
"""

from __future__ import annotations

import argparse
import csv
import sys
from typing import Iterable, List, Set


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find rows with missing values and list their company names")
    parser.add_argument("--input", default="latest_deals.csv", help="Path to input CSV (default latest_deals.csv)")
    parser.add_argument("--output", default="deals_missing.csv", help="Path to output CSV (default deals_missing.csv)")
    parser.add_argument(
        "--columns",
        default=None,
        help=(
            "Comma-separated list of columns to check for missing values."
            " If omitted, all columns in the input CSV will be checked."
        ),
    )
    return parser.parse_args()


def find_missing_rows(
    rows: Iterable[dict], columns_to_check: List[str]
) -> List[dict]:
    results: List[dict] = []
    for row in rows:
        missing_fields = [col for col in columns_to_check if (row.get(col, "").strip() == "")]
        if missing_fields:
            # add helper column for context
            row_with_missing = dict(row)
            row_with_missing["missing_fields"] = ",".join(missing_fields)
            results.append(row_with_missing)
    return results


def main() -> None:
    args = parse_args()

    try:
        with open(args.input, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            input_columns = reader.fieldnames or []
            if not input_columns:
                print("Input CSV has no headers.", file=sys.stderr)
                sys.exit(2)

            if args.columns:
                columns_to_check = [c.strip() for c in args.columns.split(",") if c.strip()]
            else:
                columns_to_check = input_columns

            rows = list(reader)
    except FileNotFoundError:
        print(f"Input CSV not found: {args.input}", file=sys.stderr)
        sys.exit(2)

    missing_rows = find_missing_rows(rows, columns_to_check)

    # Write output CSV
    output_columns = list(set(input_columns + ["missing_fields"]))
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=output_columns)
        writer.writeheader()
        writer.writerows(missing_rows)

    # Collect unique company names among missing rows
    unique_companies: Set[str] = set()
    for r in missing_rows:
        company = (r.get("company_name") or "").strip()
        if company:
            unique_companies.add(company)

    print(f"Scanned rows: {len(rows)}")
    print(f"Rows with missing values: {len(missing_rows)}")
    print(f"Unique companies (with missing values): {len(unique_companies)}")
    for name in sorted(unique_companies):
        print(f"- {name}")
    print(f"Wrote {len(missing_rows)} rows to {args.output}")


if __name__ == "__main__":
    main()


